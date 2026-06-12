"""Single source of truth for subscription plans and their limits.

`None` means unlimited. The billing UI, enforcement helpers, and webhook
plan-mapping all read from here so limits never drift across the codebase.
"""
from app.config import settings

PLAN_LIMITS = {
    "free": {"max_services": 1, "max_bookings_per_month": 30},
    "pro": {"max_services": 10, "max_bookings_per_month": None},
    "business": {"max_services": None, "max_bookings_per_month": None},
}

# For the billing page (prices in INR).
PLAN_INFO = {
    "free": {"label": "Free", "price": 0},
    "pro": {"label": "Pro", "price": 699},
    "business": {"label": "Business", "price": 1999},
}


def _limits(plan: str) -> dict:
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])


def service_limit(plan: str):
    return _limits(plan)["max_services"]


def booking_limit(plan: str):
    return _limits(plan)["max_bookings_per_month"]


def plan_for_razorpay_plan_id(plan_id: str) -> str | None:
    """Map a Razorpay Plan ID (from a webhook) back to our tier name."""
    if plan_id and plan_id == settings.razorpay_plan_pro:
        return "pro"
    if plan_id and plan_id == settings.razorpay_plan_business:
        return "business"
    return None


def razorpay_plan_id_for_tier(tier: str) -> str:
    """Map a tier name to its configured Razorpay Plan ID."""
    return {
        "pro": settings.razorpay_plan_pro,
        "business": settings.razorpay_plan_business,
    }.get(tier, "")
