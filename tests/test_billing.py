import hashlib
import hmac
import json
from datetime import datetime, timedelta

import pytest


def test_free_service_limit(client, owner_token):
    client.post("/business", json={"name": "Salon"}, headers=owner_token)
    r1 = client.post(
        "/services",
        json={"name": "Haircut", "duration_mins": 30, "price": 299},
        headers=owner_token,
    )
    r2 = client.post(
        "/services",
        json={"name": "Shave", "duration_mins": 30, "price": 99},
        headers=owner_token,
    )
    assert r1.status_code == 201
    assert r2.status_code == 403
    assert "upgrade" in r2.json()["detail"].lower()


def test_pro_allows_more_services(client, owner_token, db):
    from app.models.business import Business

    client.post("/business", json={"name": "Salon"}, headers=owner_token)
    b = db.query(Business).filter(Business.name == "Salon").first()
    b.plan = "pro"
    db.commit()
    for i in range(5):
        r = client.post(
            "/services",
            json={"name": f"S{i}", "duration_mins": 30, "price": 1},
            headers=owner_token,
        )
        assert r.status_code == 201


def test_free_booking_limit(client, shop, future_date, db):
    from app.models.business import Business
    from app.models.booking import Booking

    b = db.query(Business).filter(Business.slug == shop["slug"]).first()
    # stuff 30 confirmed bookings this month
    for i in range(30):
        db.add(
            Booking(
                business_id=b.id,
                service_id=shop["service_id"],
                customer_name=f"C{i}",
                customer_phone="1",
                start_time=datetime.utcnow(),
                end_time=datetime.utcnow() + timedelta(minutes=30),
                status="confirmed",
                manage_token=f"tok{i}",
            )
        )
    db.commit()
    first = client.get(
        f"/book/{shop['slug']}/slots",
        params={"service_id": shop["service_id"], "date": future_date},
    ).json()["slots"][0]
    r = client.post(
        f"/book/{shop['slug']}",
        json={
            "service_id": shop["service_id"],
            "customer_name": "Z",
            "customer_phone": "9",
            "start_time": first,
        },
    )
    assert r.status_code == 403


def test_billing_page_renders(client, shop):
    client.post("/login", data={"email": "owner@test.in", "password": "secret123"})
    r = client.get("/billing")
    assert r.status_code == 200
    assert "699" in r.text and "1999" in r.text
    assert client.get("/billing", follow_redirects=False).status_code in (200, 303)


def test_webhook_signature(client, shop, db, monkeypatch):
    from app.config import settings
    from app.models.business import Business

    monkeypatch.setattr(settings, "razorpay_webhook_secret", "whsec_test")
    monkeypatch.setattr(settings, "razorpay_plan_pro", "plan_PRO")

    b = db.query(Business).filter(Business.slug == shop["slug"]).first()
    b.razorpay_subscription_id = "sub_abc"
    db.commit()

    payload = {
        "event": "subscription.activated",
        "payload": {"subscription": {"entity": {"id": "sub_abc", "plan_id": "plan_PRO"}}},
    }
    body = json.dumps(payload).encode()
    sig = hmac.new(b"whsec_test", body, hashlib.sha256).hexdigest()

    # bad signature rejected
    bad = client.post(
        "/payments/webhook/razorpay",
        content=body,
        headers={"X-Razorpay-Signature": "wrong", "Content-Type": "application/json"},
    )
    assert bad.status_code == 400

    # valid signature activates the plan
    ok = client.post(
        "/payments/webhook/razorpay",
        content=body,
        headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
    )
    assert ok.status_code == 200
    db.expire_all()
    refreshed = db.query(Business).filter(Business.slug == shop["slug"]).first()
    assert refreshed.plan == "pro"
    assert refreshed.plan_status == "active"
