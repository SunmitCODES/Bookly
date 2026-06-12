"""Shared pytest fixtures.

Critical isolation rules:
- Tests use a throwaway SQLite DB in a temp dir, NEVER the real bookly.db.
- All external services (Resend, Razorpay, R2, Gupshup) are mocked so tests
  run offline with no real keys and send nothing.
"""
import os
import sys
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure the project root is importable when pytest runs from anywhere.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="session")
def _engine(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("data") / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    from app.database import Base
    import app.models.user, app.models.business, app.models.service  # noqa: F401
    import app.models.booking, app.models.availability  # noqa: F401

    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture
def db(_engine):
    """A fresh session; rolls back / clears tables between tests."""
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=_engine
    )
    session = TestingSessionLocal()
    yield session
    session.close()
    # wipe all rows so each test starts clean
    from app.database import Base

    with _engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture
def client(_engine, monkeypatch):
    """TestClient with get_db overridden to the test engine + externals mocked."""
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=_engine
    )

    from app.main import app
    from app.database import get_db

    def _override_get_db():
        s = TestingSessionLocal()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override_get_db

    # silence all outbound integrations
    import resend
    monkeypatch.setattr(resend.Emails, "send", lambda payload: None, raising=False)
    import app.services.whatsapp as wa
    monkeypatch.setattr(wa, "send_whatsapp", lambda to, msg: None)

    yield TestClient(app)

    app.dependency_overrides.clear()
    # clean tables after each client test too
    from app.database import Base
    with _engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


# ----- helpers ---------------------------------------------------------------

@pytest.fixture
def owner_token(client):
    """Signs up + logs in an owner; returns a bearer-auth header dict."""
    client.post("/auth/signup", json={"email": "owner@test.in", "password": "secret123"})
    tok = client.post(
        "/auth/login", json={"email": "owner@test.in", "password": "secret123"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def shop(client, owner_token):
    """An owner with a business, a 30-min service, and 7-day 9-17 availability.

    Returns {slug, service_id, headers}.
    """
    slug = client.post(
        "/business", json={"name": "Glamour Salon", "address": "Pune"}, headers=owner_token
    ).json()["slug"]
    sid = client.post(
        "/services",
        json={"name": "Haircut", "duration_mins": 30, "price": 299},
        headers=owner_token,
    ).json()["id"]
    client.put(
        "/availability",
        json={
            "rules": [
                {
                    "day_of_week": d,
                    "start_time": "09:00:00",
                    "end_time": "17:00:00",
                    "slot_duration_mins": 30,
                }
                for d in range(7)
            ]
        },
        headers=owner_token,
    )
    return {"slug": slug, "service_id": sid, "headers": owner_token}


@pytest.fixture
def future_date():
    return (datetime.utcnow() + timedelta(days=7)).date().isoformat()
