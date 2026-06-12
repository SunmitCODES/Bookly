def _first_slot(client, shop, future_date):
    return client.get(
        f"/book/{shop['slug']}/slots",
        params={"service_id": shop["service_id"], "date": future_date},
    ).json()["slots"][0]


def test_slots_generated(client, shop, future_date):
    r = client.get(
        f"/book/{shop['slug']}/slots",
        params={"service_id": shop["service_id"], "date": future_date},
    )
    assert r.status_code == 200
    slots = r.json()["slots"]
    # 9-17 in 30-min steps for a 30-min service => 16 slots (last 16:30)
    assert len(slots) == 16
    assert slots[-1].endswith("16:30:00")


def test_book_then_slot_consumed(client, shop, future_date):
    first = _first_slot(client, shop, future_date)
    r = client.post(
        f"/book/{shop['slug']}",
        json={
            "service_id": shop["service_id"],
            "customer_name": "Asha",
            "customer_phone": "+91981",
            "start_time": first,
        },
    )
    assert r.status_code == 201
    assert r.json()["end_time"].endswith("09:30:00")
    slots = client.get(
        f"/book/{shop['slug']}/slots",
        params={"service_id": shop["service_id"], "date": future_date},
    ).json()["slots"]
    assert first not in slots


def test_double_book_conflict(client, shop, future_date):
    first = _first_slot(client, shop, future_date)
    body = {
        "service_id": shop["service_id"],
        "customer_name": "X",
        "customer_phone": "1",
        "start_time": first,
    }
    assert client.post(f"/book/{shop['slug']}", json=body).status_code == 201
    assert client.post(f"/book/{shop['slug']}", json=body).status_code == 409


def test_unknown_business_404(client):
    assert client.get("/book/nope").status_code == 404


def test_owner_sees_bookings(client, shop, future_date):
    first = _first_slot(client, shop, future_date)
    client.post(
        f"/book/{shop['slug']}",
        json={
            "service_id": shop["service_id"],
            "customer_name": "Asha",
            "customer_phone": "+91981",
            "start_time": first,
        },
    )
    r = client.get("/bookings", headers=shop["headers"])
    assert r.status_code == 200 and len(r.json()) == 1
    assert client.get("/bookings").status_code == 401  # unauth


def test_customer_cancel_frees_slot(client, shop, future_date, db):
    from app.models.booking import Booking

    first = _first_slot(client, shop, future_date)
    client.post(
        f"/book/{shop['slug']}",
        json={
            "service_id": shop["service_id"],
            "customer_name": "Asha",
            "customer_phone": "+91981",
            "start_time": first,
        },
    )
    token = db.query(Booking).filter(Booking.customer_name == "Asha").first().manage_token
    assert client.get(f"/booking/{token}").status_code == 200
    assert client.get("/booking/bogus").status_code == 404
    r = client.post(f"/booking/{token}/cancel")
    assert r.status_code == 200 and "cancelled" in r.text.lower()
    slots = client.get(
        f"/book/{shop['slug']}/slots",
        params={"service_id": shop["service_id"], "date": future_date},
    ).json()["slots"]
    assert first in slots  # freed


def test_owner_reschedule(client, shop, future_date, db):
    from app.models.booking import Booking

    first = _first_slot(client, shop, future_date)
    client.post(
        f"/book/{shop['slug']}",
        json={
            "service_id": shop["service_id"],
            "customer_name": "Meena",
            "customer_phone": "+91983",
            "start_time": first,
        },
    )
    bid = str(db.query(Booking).filter(Booking.customer_name == "Meena").first().id)
    client.post("/login", data={"email": "owner@test.in", "password": "secret123"})

    slots = client.get(
        f"/book/{shop['slug']}/slots",
        params={"service_id": shop["service_id"], "date": future_date},
    ).json()["slots"]
    new_slot = slots[1]
    r = client.post(
        f"/dashboard/bookings/{bid}/reschedule", data={"start_time": new_slot}
    )
    assert r.status_code == 200
    after = client.get(
        f"/book/{shop['slug']}/slots",
        params={"service_id": shop["service_id"], "date": future_date},
    ).json()["slots"]
    assert first in after  # old freed
    assert new_slot not in after  # new consumed
