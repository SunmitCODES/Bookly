"""Slot generation engine — the core booking logic.

Pure-ish functions that take a DB session plus domain objects and compute
which start times are bookable. Kept free of FastAPI imports so the logic
is easy to test and is reused by both the public /slots endpoint and the
booking-creation validation.
"""
from datetime import datetime, date, timedelta

from sqlalchemy.orm import Session

from app.models.availability import Availability
from app.models.booking import Booking
from app.models.service import Service


def _intervals_overlap(a_start, a_end, b_start, b_end) -> bool:
    """True if [a_start, a_end) overlaps [b_start, b_end).

    Touching intervals (one ends exactly when the other starts) do NOT
    overlap — that's what allows back-to-back bookings.
    """
    return a_start < b_end and b_start < a_end


def _day_bookings(
    db: Session, business_id, target_date: date, exclude_booking_id=None
) -> list[Booking]:
    """All non-cancelled bookings for a business on a given calendar date.

    `exclude_booking_id` skips a specific booking — used when rescheduling
    so a booking doesn't conflict with its own current slot.
    """
    day_start = datetime.combine(target_date, datetime.min.time())
    day_end = day_start + timedelta(days=1)
    q = db.query(Booking).filter(
        Booking.business_id == business_id,
        Booking.status != "cancelled",
        Booking.start_time >= day_start,
        Booking.start_time < day_end,
    )
    if exclude_booking_id is not None:
        q = q.filter(Booking.id != exclude_booking_id)
    return q.all()


def generate_slots(
    db: Session,
    business_id,
    service: Service,
    target_date: date,
    exclude_booking_id=None,
) -> list[datetime]:
    """Return the list of bookable start datetimes for a service on a date."""
    rule = (
        db.query(Availability)
        .filter(
            Availability.business_id == business_id,
            Availability.day_of_week == target_date.weekday(),  # 0=Mon..6=Sun
            Availability.is_active == True,  # noqa: E712 (SQLAlchemy needs ==)
        )
        .first()
    )
    if rule is None:
        return []  # closed that day

    duration = timedelta(minutes=service.duration_mins)
    step = timedelta(minutes=rule.slot_duration_mins)

    window_start = datetime.combine(target_date, rule.start_time)
    window_end = datetime.combine(target_date, rule.end_time)
    now = datetime.utcnow()

    existing = _day_bookings(db, business_id, target_date, exclude_booking_id)

    slots: list[datetime] = []
    candidate = window_start
    while candidate + duration <= window_end:
        slot_end = candidate + duration
        # skip past times
        if candidate < now:
            candidate += step
            continue
        # skip if it overlaps any existing booking
        clash = any(
            _intervals_overlap(candidate, slot_end, b.start_time, b.end_time)
            for b in existing
        )
        if not clash:
            slots.append(candidate)
        candidate += step

    return slots


def is_slot_available(
    db: Session,
    business_id,
    service: Service,
    start_time: datetime,
    exclude_booking_id=None,
) -> bool:
    """True if `start_time` is a real, currently-bookable slot for the service.

    Reuses generate_slots so a single requested time is validated against
    exactly the same rules the customer was offered. `exclude_booking_id`
    lets a reschedule ignore the booking's own current slot.
    """
    valid_slots = generate_slots(
        db, business_id, service, start_time.date(), exclude_booking_id
    )
    return start_time in valid_slots
