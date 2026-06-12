import secrets
from uuid import UUID
from datetime import datetime, date, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.notifications import (
    send_booking_confirmation,
    send_owner_notification,
)
from app.dependencies import get_current_business
from app.models.business import Business
from app.models.service import Service
from app.models.booking import Booking
from app.schemas.booking import (
    BookingCreate,
    BookingOut,
    PublicBusinessOut,
    SlotsOut,
)
from app.services.slot_engine import generate_slots, is_slot_available
from app.services.billing import can_add_booking

router = APIRouter(tags=["Bookings"])


# ----- helpers ---------------------------------------------------------------

def _get_business_by_slug(slug: str, db: Session) -> Business:
    business = db.query(Business).filter(Business.slug == slug).first()
    if business is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Business not found."
        )
    return business


def _get_business_service(business: Business, service_id: UUID, db: Session) -> Service:
    service = (
        db.query(Service)
        .filter(Service.id == service_id, Service.business_id == business.id)
        .first()
    )
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found for this business.",
        )
    return service


# ----- PUBLIC (no auth), keyed by business slug ------------------------------

@router.get("/book/{slug}", response_model=PublicBusinessOut)
def public_business_info(slug: str, db: Session = Depends(get_db)):
    business = _get_business_by_slug(slug, db)
    services = db.query(Service).filter(Service.business_id == business.id).all()
    return PublicBusinessOut(
        name=business.name,
        slug=business.slug,
        phone=business.phone,
        address=business.address,
        logo_url=business.logo_url,
        services=services,
    )


@router.get("/book/{slug}/slots", response_model=SlotsOut)
def public_available_slots(
    slug: str,
    service_id: UUID = Query(...),
    date: date = Query(..., description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    business = _get_business_by_slug(slug, db)
    service = _get_business_service(business, service_id, db)
    slots = generate_slots(db, business.id, service, date)
    return SlotsOut(date=date.isoformat(), service_id=service_id, slots=slots)


@router.post("/book/{slug}", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
def create_booking(
    slug: str,
    data: BookingCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    business = _get_business_by_slug(slug, db)
    service = _get_business_service(business, data.service_id, db)

    ok, reason = can_add_booking(db, business)
    if not ok:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=reason)

    if not is_slot_available(db, business.id, service, data.start_time):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That time is no longer available.",
        )

    booking = Booking(
        business_id=business.id,
        service_id=service.id,
        customer_name=data.customer_name,
        customer_phone=data.customer_phone,
        customer_email=data.customer_email or None,
        start_time=data.start_time,
        end_time=data.start_time + timedelta(minutes=service.duration_mins),
        status="confirmed",
        manage_token=secrets.token_urlsafe(16),
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    # Capture primitives now, while the session is open — the background
    # tasks run after the response, when ORM objects are no longer usable.
    owner_email = business.owner.email
    business_name = business.name
    business_address = business.address
    service_name = service.name

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
    )
    background_tasks.add_task(
        send_owner_notification,
        owner_email=owner_email,
        customer_name=booking.customer_name,
        customer_phone=booking.customer_phone,
        service_name=service_name,
        start_time=booking.start_time,
    )

    return booking


# ----- OWNER (auth) ----------------------------------------------------------

@router.get("/bookings", response_model=list[BookingOut], tags=["Bookings"])
def list_my_bookings(
    booking_date: date | None = Query(None, alias="date", description="YYYY-MM-DD"),
    status_filter: str | None = Query(None, alias="status"),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    q = db.query(Booking).filter(Booking.business_id == business.id)
    if status_filter:
        q = q.filter(Booking.status == status_filter)
    if booking_date:
        day_start = datetime.combine(booking_date, datetime.min.time())
        q = q.filter(
            Booking.start_time >= day_start,
            Booking.start_time < day_start + timedelta(days=1),
        )
    return q.order_by(Booking.start_time.desc()).all()
