from datetime import datetime, timedelta

import pytest


@pytest.fixture
def seeded(db):
    """Create a business + service and helper to add bookings."""
    from app.models.user import User
    from app.models.business import Business
    from app.models.service import Service
    from app.services.auth import hash_password

    u = User(email="o@r.in", hashed_password=hash_password("x"))
    db.add(u)
    db.commit()
    db.refresh(u)
    b = Business(owner_id=u.id, name="Salon", slug="salon-r")
    db.add(b)
    db.commit()
    db.refresh(b)
    s = Service(business_id=b.id, name="Cut", duration_mins=30, price=1)
    db.add(s)
    db.commit()
    db.refresh(s)

    def add(name, start, status="confirmed", reminded=False, email="c@e.com"):
        from app.models.booking import Booking

        db.add(
            Booking(
                business_id=b.id,
                service_id=s.id,
                customer_name=name,
                customer_phone="+91999",
                customer_email=email,
                start_time=start,
                end_time=start + timedelta(minutes=30),
                status=status,
                reminder_sent=reminded,
                manage_token=name,
            )
        )
        db.commit()

    return add


def test_due_reminders_selection(db, seeded):
    from app.tasks.reminder_tasks import due_reminders

    now = datetime.utcnow()
    seeded("due_soon", now + timedelta(hours=12))
    seeded("due_edge", now + timedelta(hours=23))
    seeded("too_far", now + timedelta(hours=48))
    seeded("in_past", now - timedelta(hours=1))
    seeded("cancelled", now + timedelta(hours=5), status="cancelled")
    seeded("already", now + timedelta(hours=5), reminded=True)

    names = sorted(b.customer_name for b in due_reminders(db, now))
    assert names == ["due_edge", "due_soon"]


def test_sweep_sends_and_marks_once(db, seeded, monkeypatch):
    import app.tasks.reminder_tasks as rt

    emails, whats = [], []
    monkeypatch.setattr(
        rt, "send_booking_reminder", lambda **kw: emails.append(kw["customer_email"])
    )
    monkeypatch.setattr(rt, "send_whatsapp", lambda to, msg: whats.append(to))
    # sweep opens its own SessionLocal; point it at our test session's bind
    from sqlalchemy.orm import sessionmaker

    monkeypatch.setattr(
        rt, "SessionLocal", sessionmaker(bind=db.get_bind())
    )

    now = datetime.utcnow()
    seeded("a", now + timedelta(hours=5))
    seeded("b", now + timedelta(hours=10))

    sent = rt.sweep_reminders()
    assert sent == 2
    assert len(emails) == 2 and len(whats) == 2

    # idempotent: second run sends nothing
    emails.clear()
    assert rt.sweep_reminders() == 0


def test_whatsapp_blank_key_no_op():
    """send_whatsapp must not raise when unconfigured."""
    from app.services.whatsapp import send_whatsapp

    send_whatsapp("+91999", "hi")  # blank key in test config -> no-op, no raise
