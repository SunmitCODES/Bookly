import secrets
from uuid import UUID
from datetime import datetime, date, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_business_web, get_current_user_web
from app.models.user import User
from app.models.business import Business
from app.models.service import Service
from app.models.availability import Availability
from app.models.booking import Booking
from app.routers.bookings import _get_business_by_slug, _get_business_service
from app.routers.business import _save_logo, _slugify, _unique_slug
from app.services.storage import is_configured as storage_configured
from app.services.slot_engine import generate_slots, is_slot_available
from app.services.billing import can_add_booking, can_add_service
from app.services.notifications import (
    send_booking_confirmation,
    send_owner_notification,
    send_cancellation,
    send_reschedule,
)
from app.templating import templates

router = APIRouter(tags=["Pages"])


# ----- Owner dashboard (cookie auth) -----------------------------------------

@router.get("/dashboard")
def dashboard(
    request: Request,
    business: Business = Depends(get_current_business_web),
    db: Session = Depends(get_db),
):
    bookings = (
        db.query(Booking)
        .filter(Booking.business_id == business.id)
        .order_by(Booking.start_time.desc())
        .all()
    )
    public_link = str(request.base_url).rstrip("/") + f"/b/{business.slug}"
    return templates.TemplateResponse(
        request,
        "owner/dashboard.html",
        {
            "business": business,
            "bookings": bookings,
            "public_link": public_link,
            "storage_configured": storage_configured(),
        },
    )


@router.post("/dashboard/logo")
def dashboard_upload_logo(
    request: Request,
    file: UploadFile = File(...),
    business: Business = Depends(get_current_business_web),
    db: Session = Depends(get_db),
):
    _save_logo(business, file, db)  # raises HTTPException on bad/unconfigured
    return templates.TemplateResponse(
        request, "owner/_logo_card.html", {"business": business}
    )


# ----- Owner setup pages (cookie auth; user required, business optional) -----

@router.get("/setup/business")
def setup_business_page(
    request: Request,
    current_user: User = Depends(get_current_user_web),
    db: Session = Depends(get_db),
):
    existing = (
        db.query(Business).filter(Business.owner_id == current_user.id).first()
    )
    if existing is not None:
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse(request, "owner/setup_business.html", {})


@router.post("/setup/business")
def setup_business_submit(
    request: Request,
    name: str = Form(...),
    phone: str = Form(""),
    address: str = Form(""),
    current_user: User = Depends(get_current_user_web),
    db: Session = Depends(get_db),
):
    if db.query(Business).filter(Business.owner_id == current_user.id).first():
        return RedirectResponse(url="/dashboard", status_code=303)
    business = Business(
        owner_id=current_user.id,
        name=name,
        slug=_unique_slug(db, _slugify(name)),
        phone=phone or None,
        address=address or None,
    )
    db.add(business)
    db.commit()
    return RedirectResponse(url="/setup/services", status_code=303)


@router.get("/setup/services")
def setup_services_page(
    request: Request,
    business: Business = Depends(get_current_business_web),
    db: Session = Depends(get_db),
):
    services = db.query(Service).filter(Service.business_id == business.id).all()
    return templates.TemplateResponse(
        request,
        "owner/setup_services.html",
        {"business": business, "services": services},
    )


@router.post("/setup/services")
def setup_services_add(
    request: Request,
    name: str = Form(...),
    duration_mins: int = Form(...),
    price: float = Form(...),
    business: Business = Depends(get_current_business_web),
    db: Session = Depends(get_db),
):
    ok, reason = can_add_service(db, business)
    error = None if ok else reason
    if ok:
        db.add(
            Service(
                business_id=business.id,
                name=name,
                duration_mins=duration_mins,
                price=price,
            )
        )
        db.commit()
    services = db.query(Service).filter(Service.business_id == business.id).all()
    return templates.TemplateResponse(
        request,
        "owner/_services_list.html",
        {"business": business, "services": services, "error": error},
    )


@router.post("/setup/services/{service_id}/delete")
def setup_services_delete(
    service_id: UUID,
    request: Request,
    business: Business = Depends(get_current_business_web),
    db: Session = Depends(get_db),
):
    svc = (
        db.query(Service)
        .filter(Service.id == service_id, Service.business_id == business.id)
        .first()
    )
    if svc is not None:
        db.delete(svc)
        db.commit()
    services = db.query(Service).filter(Service.business_id == business.id).all()
    return templates.TemplateResponse(
        request,
        "owner/_services_list.html",
        {"business": business, "services": services},
    )


_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


@router.get("/setup/availability")
def setup_availability_page(
    request: Request,
    business: Business = Depends(get_current_business_web),
    db: Session = Depends(get_db),
):
    rows = {
        a.day_of_week: a
        for a in db.query(Availability).filter(
            Availability.business_id == business.id
        )
    }
    days = []
    for i, label in enumerate(_DAYS):
        a = rows.get(i)
        days.append(
            {
                "index": i,
                "label": label,
                "active": a.is_active if a else (i < 6),
                "start": (a.start_time.strftime("%H:%M") if a else "10:00"),
                "end": (a.end_time.strftime("%H:%M") if a else "19:00"),
                "slot": (a.slot_duration_mins if a else 30),
            }
        )
    return templates.TemplateResponse(
        request, "owner/setup_availability.html", {"business": business, "days": days}
    )


@router.post("/setup/availability")
async def setup_availability_submit(
    request: Request,
    business: Business = Depends(get_current_business_web),
    db: Session = Depends(get_db),
):
    from datetime import time as _time

    form = await request.form()
    # wipe + rebuild this business's weekly schedule
    db.query(Availability).filter(
        Availability.business_id == business.id
    ).delete()
    for i in range(7):
        if form.get(f"active_{i}") != "on":
            continue
        start = form.get(f"start_{i}", "10:00")
        end = form.get(f"end_{i}", "19:00")
        slot = int(form.get(f"slot_{i}", 30))
        sh, sm = (int(x) for x in start.split(":"))
        eh, em = (int(x) for x in end.split(":"))
        db.add(
            Availability(
                business_id=business.id,
                day_of_week=i,
                start_time=_time(sh, sm),
                end_time=_time(eh, em),
                slot_duration_mins=slot,
                is_active=True,
            )
        )
    db.commit()
    return RedirectResponse(url="/dashboard", status_code=303)


# ----- Public booking page (no auth), under /b/{slug} ------------------------

@router.get("/b/{slug}")
def public_book_page(slug: str, request: Request, db: Session = Depends(get_db)):
    business = _get_business_by_slug(slug, db)
    services = db.query(Service).filter(Service.business_id == business.id).all()
    return templates.TemplateResponse(
        request,
        "public/book.html",
        {"business": business, "services": services},
    )


@router.get("/b/{slug}/slots-partial")
def public_slots_partial(
    slug: str,
    request: Request,
    service_id: UUID = Query(...),
    date: date = Query(...),
    db: Session = Depends(get_db),
):
    business = _get_business_by_slug(slug, db)
    service = _get_business_service(business, service_id, db)
    slots = generate_slots(db, business.id, service, date)
    return templates.TemplateResponse(
        request,
        "public/_slots.html",
        {
            "slug": slug,
            "service_id": service_id,
            "date": date.isoformat(),
            "slots": slots,
        },
    )


@router.get("/b/{slug}/booking-form")
def public_booking_form(
    slug: str,
    request: Request,
    service_id: UUID = Query(...),
    start_time: datetime = Query(...),
):
    return templates.TemplateResponse(
        request,
        "public/_booking_form.html",
        {
            "slug": slug,
            "service_id": service_id,
            "start_time": start_time,
        },
    )


@router.post("/b/{slug}/book")
def public_book_submit(
    slug: str,
    request: Request,
    background_tasks: BackgroundTasks,
    service_id: UUID = Form(...),
    start_time: datetime = Form(...),
    customer_name: str = Form(...),
    customer_phone: str = Form(...),
    customer_email: str = Form(""),
    db: Session = Depends(get_db),
):
    business = _get_business_by_slug(slug, db)
    service = _get_business_service(business, service_id, db)

    ok, reason = can_add_booking(db, business)
    if not ok:
        return templates.TemplateResponse(
            request,
            "public/_slots.html",
            {
                "slug": slug,
                "service_id": service_id,
                "date": start_time.date().isoformat(),
                "slots": generate_slots(db, business.id, service, start_time.date()),
                "error": reason,
            },
        )

    if not is_slot_available(db, business.id, service, start_time):
        return templates.TemplateResponse(
            request,
            "public/_slots.html",
            {
                "slug": slug,
                "service_id": service_id,
                "date": start_time.date().isoformat(),
                "slots": generate_slots(db, business.id, service, start_time.date()),
            },
        )

    booking = Booking(
        business_id=business.id,
        service_id=service.id,
        customer_name=customer_name,
        customer_phone=customer_phone,
        customer_email=customer_email or None,
        start_time=start_time,
        end_time=start_time + timedelta(minutes=service.duration_mins),
        status="confirmed",
        manage_token=secrets.token_urlsafe(16),
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    owner_email = business.owner.email
    business_name = business.name
    business_address = business.address
    service_name = service.name
    manage_url = str(request.base_url).rstrip("/") + f"/booking/{booking.manage_token}"

    background_tasks.add_task(
        send_booking_confirmation,
        customer_email=booking.customer_email,
        customer_name=booking.customer_name,
        business_name=business_name,
        service_name=service_name,
        start_time=booking.start_time,
        end_time=booking.end_time,
        business_address=business_address,
        booking_id=str(booking.id),
        manage_url=manage_url,
    )
    background_tasks.add_task(
        send_owner_notification,
        owner_email=owner_email,
        customer_name=booking.customer_name,
        customer_phone=booking.customer_phone,
        service_name=service_name,
        start_time=booking.start_time,
    )

    return templates.TemplateResponse(
        request,
        "public/_confirmation.html",
        {"booking": booking, "service_name": service_name},
    )


# ----- shared cancel logic ---------------------------------------------------

def _notify_cancellation(background_tasks, booking, business, service):
    """Queue cancellation emails to both customer and owner."""
    background_tasks.add_task(
        send_cancellation,
        to_email=booking.customer_email,
        customer_name=booking.customer_name,
        business_name=business.name,
        service_name=service.name,
        start_time=booking.start_time,
        is_owner=False,
    )
    background_tasks.add_task(
        send_cancellation,
        to_email=business.owner.email,
        customer_name=booking.customer_name,
        business_name=business.name,
        service_name=service.name,
        start_time=booking.start_time,
        is_owner=True,
    )


# ----- Customer self-service cancel (public, secret token) -------------------

@router.get("/booking/{token}")
def manage_booking_page(token: str, request: Request, db: Session = Depends(get_db)):
    booking = db.query(Booking).filter(Booking.manage_token == token).first()
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found.")
    business = db.query(Business).filter(Business.id == booking.business_id).first()
    service = db.query(Service).filter(Service.id == booking.service_id).first()
    return templates.TemplateResponse(
        request,
        "public/manage.html",
        {"booking": booking, "business": business, "service": service, "token": token},
    )


@router.post("/booking/{token}/cancel")
def manage_booking_cancel(
    token: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    booking = db.query(Booking).filter(Booking.manage_token == token).first()
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found.")
    business = db.query(Business).filter(Business.id == booking.business_id).first()
    service = db.query(Service).filter(Service.id == booking.service_id).first()

    if booking.status != "cancelled":
        booking.status = "cancelled"
        db.commit()
        _notify_cancellation(background_tasks, booking, business, service)

    return templates.TemplateResponse(
        request, "public/_cancelled.html", {"booking": booking}
    )


# ----- Owner cancel + reschedule (cookie auth) -------------------------------

def _owner_booking(booking_id: UUID, business: Business, db: Session) -> Booking:
    booking = (
        db.query(Booking)
        .filter(Booking.id == booking_id, Booking.business_id == business.id)
        .first()
    )
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found.")
    return booking


def _render_bookings_table(request, business, db):
    bookings = (
        db.query(Booking)
        .filter(Booking.business_id == business.id)
        .order_by(Booking.start_time.desc())
        .all()
    )
    return templates.TemplateResponse(
        request,
        "owner/_bookings_table.html",
        {"business": business, "bookings": bookings},
    )


@router.post("/dashboard/bookings/{booking_id}/cancel")
def owner_cancel(
    booking_id: UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    business: Business = Depends(get_current_business_web),
    db: Session = Depends(get_db),
):
    booking = _owner_booking(booking_id, business, db)
    service = db.query(Service).filter(Service.id == booking.service_id).first()
    if booking.status != "cancelled":
        booking.status = "cancelled"
        db.commit()
        _notify_cancellation(background_tasks, booking, business, service)
    return _render_bookings_table(request, business, db)


@router.get("/dashboard/bookings/{booking_id}/reschedule")
def owner_reschedule_form(
    booking_id: UUID,
    request: Request,
    date: date | None = Query(None),
    business: Business = Depends(get_current_business_web),
    db: Session = Depends(get_db),
):
    booking = _owner_booking(booking_id, business, db)
    service = db.query(Service).filter(Service.id == booking.service_id).first()
    target = date or booking.start_time.date()
    slots = generate_slots(db, business.id, service, target, exclude_booking_id=booking.id)
    return templates.TemplateResponse(
        request,
        "owner/_reschedule.html",
        {
            "booking": booking,
            "service": service,
            "date": target.isoformat(),
            "slots": slots,
        },
    )


@router.post("/dashboard/bookings/{booking_id}/reschedule")
def owner_reschedule_submit(
    booking_id: UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    start_time: datetime = Form(...),
    business: Business = Depends(get_current_business_web),
    db: Session = Depends(get_db),
):
    booking = _owner_booking(booking_id, business, db)
    service = db.query(Service).filter(Service.id == booking.service_id).first()

    if not is_slot_available(
        db, business.id, service, start_time, exclude_booking_id=booking.id
    ):
        # conflict — re-render the slot picker for that day
        slots = generate_slots(
            db, business.id, service, start_time.date(), exclude_booking_id=booking.id
        )
        return templates.TemplateResponse(
            request,
            "owner/_reschedule.html",
            {
                "booking": booking,
                "service": service,
                "date": start_time.date().isoformat(),
                "slots": slots,
                "error": "That time is not available.",
            },
        )

    old_start = booking.start_time
    booking.start_time = start_time
    booking.end_time = start_time + timedelta(minutes=service.duration_mins)
    db.commit()
    db.refresh(booking)

    background_tasks.add_task(
        send_reschedule,
        customer_email=booking.customer_email,
        customer_name=booking.customer_name,
        business_name=business.name,
        service_name=service.name,
        old_start=old_start,
        new_start=booking.start_time,
        new_end=booking.end_time,
        business_address=business.address,
        booking_id=str(booking.id),
    )
    return _render_bookings_table(request, business, db)
