import json
import logging

import razorpay
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_business_web
from app.models.business import Business
from app.plans import (
    PLAN_INFO,
    razorpay_plan_id_for_tier,
    plan_for_razorpay_plan_id,
)
from app.services.billing import verify_webhook
from app.templating import templates

logger = logging.getLogger("bookly.payments")

router = APIRouter(tags=["Payments"])


def _client() -> razorpay.Client:
    return razorpay.Client(
        auth=(settings.razorpay_key_id, settings.razorpay_key_secret)
    )


# ----- Billing page + subscribe (cookie auth) --------------------------------

@router.get("/billing")
def billing_page(
    request: Request,
    business: Business = Depends(get_current_business_web),
):
    return templates.TemplateResponse(
        request,
        "owner/billing.html",
        {"business": business, "plans": PLAN_INFO},
    )


@router.post("/billing/subscribe")
def subscribe(
    request: Request,
    tier: str = Form(...),
    business: Business = Depends(get_current_business_web),
    db: Session = Depends(get_db),
):
    if tier not in ("pro", "business"):
        raise HTTPException(status_code=400, detail="Unknown plan.")
    plan_id = razorpay_plan_id_for_tier(tier)
    if not plan_id:
        raise HTTPException(
            status_code=400,
            detail="This plan is not configured yet. Add its Razorpay Plan ID.",
        )

    sub = _client().subscription.create(
        {
            "plan_id": plan_id,
            "total_count": 12,  # bill monthly for up to a year, then renew
            "customer_notify": 1,
        }
    )

    business.razorpay_subscription_id = sub["id"]
    business.plan_status = "created"
    db.commit()

    return templates.TemplateResponse(
        request,
        "owner/_checkout.html",
        {
            "subscription_id": sub["id"],
            "razorpay_key_id": settings.razorpay_key_id,
            "tier": tier,
        },
    )


# ----- Webhook (public, signature-verified) ----------------------------------

@router.post("/payments/webhook/razorpay")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    if not verify_webhook(body, signature):
        raise HTTPException(status_code=400, detail="Invalid signature.")

    event = json.loads(body)
    event_type = event.get("event", "")

    sub_entity = (
        event.get("payload", {}).get("subscription", {}).get("entity", {})
    )
    sub_id = sub_entity.get("id")
    plan_id = sub_entity.get("plan_id")

    if not sub_id:
        return JSONResponse({"status": "ignored"})

    business = (
        db.query(Business)
        .filter(Business.razorpay_subscription_id == sub_id)
        .first()
    )
    if business is None:
        logger.warning("Webhook for unknown subscription %s", sub_id)
        return JSONResponse({"status": "ignored"})

    if event_type in ("subscription.activated", "subscription.charged"):
        tier = plan_for_razorpay_plan_id(plan_id)
        if tier:
            business.plan = tier
        business.plan_status = "active"
    elif event_type in ("subscription.cancelled", "subscription.completed"):
        business.plan = "free"
        business.plan_status = "cancelled"
    elif event_type in ("subscription.halted", "subscription.paused"):
        business.plan_status = "halted"
    else:
        return JSONResponse({"status": "ignored"})

    db.commit()
    return JSONResponse({"status": "ok"})
