"""Plan-enforcement helpers and Razorpay webhook signature verification.

The enforcement rules live here (one place) and are reused by both the API
and HTML creation paths.
"""
import hashlib
import hmac
from datetime import datetime

from sqlalchemy.orm import Session

from app.config import settings
from app.models.service import Service
from app.models.booking import Booking
from app.plans import service_limit, booking_limit


def can_add_service(db: Session, business) -> tuple[bool, str]:
    limit = service_limit(business.plan)
    if limit is None:
        return True, ""
    count = db.query(Service).filter(Service.business_id == business.id).count()
    if count >= limit:
        return (
            False,
            f"Your {business.plan.title()} plan allows {limit} "
            f"service{'s' if limit != 1 else ''}. Upgrade to add more.",
        )
    return True, ""


def can_add_booking(db: Session, business) -> tuple[bool, str]:
    limit = booking_limit(business.plan)
    if limit is None:
        return True, ""
    # count confirmed bookings created in the current calendar month
    now = datetime.utcnow()
    month_start = datetime(now.year, now.month, 1)
    count = (
        db.query(Booking)
        .filter(
            Booking.business_id == business.id,
            Booking.status != "cancelled",
            Booking.created_at >= month_start,
        )
        .count()
    )
    if count >= limit:
        return (
            False,
            "This business has reached its monthly booking limit. "
            "Please contact them directly.",
        )
    return True, ""


def verify_webhook(body: bytes, signature: str) -> bool:
    """Verify a Razorpay webhook payload signature (HMAC-SHA256)."""
    secret = settings.razorpay_webhook_secret
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
