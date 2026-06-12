"""The reminder sweep: find bookings ~lead_hours out and remind once each."""
import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.booking import Booking
from app.services.notifications import send_booking_reminder
from app.services.whatsapp import send_whatsapp
from app.tasks.celery_app import celery_app

logger = logging.getLogger("bookly.reminders")


def due_reminders(db: Session, now: datetime) -> list[Booking]:
    """Confirmed, unreminded bookings starting within the lead window.

    Pure selection logic (no sending) so it can be unit-tested directly.
    """
    cutoff = now + timedelta(hours=settings.reminder_lead_hours)
    return (
        db.query(Booking)
        .filter(
            Booking.status == "confirmed",
            Booking.reminder_sent == False,  # noqa: E712
            Booking.start_time > now,
            Booking.start_time <= cutoff,
        )
        .all()
    )


def _send_for(booking: Booking) -> None:
    business_name = booking.business.name
    service_name = booking.service.name
    send_booking_reminder(
        customer_email=booking.customer_email,
        customer_name=booking.customer_name,
        business_name=business_name,
        service_name=service_name,
        start_time=booking.start_time,
    )
    send_whatsapp(
        booking.customer_phone,
        f"Reminder: your {service_name} at {business_name} is coming up. See you soon!",
    )


@celery_app.task(name="app.tasks.reminder_tasks.sweep_reminders")
def sweep_reminders() -> int:
    """Send reminders for all due bookings; return how many were sent."""
    db = SessionLocal()
    sent = 0
    try:
        now = datetime.utcnow()
        for booking in due_reminders(db, now):
            _send_for(booking)  # send helpers never raise
            booking.reminder_sent = True
            sent += 1
        db.commit()
    finally:
        db.close()
    logger.info("sweep_reminders sent %d reminder(s)", sent)
    return sent
