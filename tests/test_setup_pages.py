"""The browser self-serve onboarding flow: signup -> business -> services -> hours."""


def _web_signup(client, email="newowner@test.in"):
    client.post("/auth/signup", json={"email": email, "password": "secret123"})
    client.post("/login", data={"email": email, "password": "secret123"})


def test_new_owner_redirected_to_setup(client):
    _web_signup(client)
    # logged in but no business -> dashboard sends to /setup/business (not /login)
    r = client.get("/dashboard", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/setup/business"


def test_setup_business_page_renders(client):
    _web_signup(client)
    r = client.get("/setup/business")
    assert r.status_code == 200 and "business" in r.text.lower()


def test_full_self_serve_onboarding(client):
    _web_signup(client)

    # 1. create business -> redirect to services
    r = client.post(
        "/setup/business",
        data={"name": "Sharma Hair Studio", "address": "FC Road"},
        follow_redirects=False,
    )
    assert r.status_code == 303 and r.headers["location"] == "/setup/services"

    # 2. dashboard now works (has a business)
    assert client.get("/dashboard", follow_redirects=False).status_code == 200

    # 3. add a service via the setup page (HTMX partial)
    r = client.post(
        "/setup/services",
        data={"name": "Haircut", "duration_mins": 30, "price": 300},
    )
    assert r.status_code == 200 and "Haircut" in r.text

    # 4. set availability -> redirect to dashboard
    form = {}
    for i in range(6):  # Mon-Sat open
        form[f"active_{i}"] = "on"
        form[f"start_{i}"] = "10:00"
        form[f"end_{i}"] = "19:00"
        form[f"slot_{i}"] = "30"
    r = client.post("/setup/availability", data=form, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/dashboard"

    # 5. the public booking page now offers real slots
    biz = client.get("/business/me")  # cookie auth not on this API route; use bearer
    # fetch slug from dashboard instead
    dash = client.get("/dashboard").text
    assert "/b/sharma-hair-studio" in dash

    import datetime as dt

    info = client.get("/book/sharma-hair-studio").json()
    sid = info["services"][0]["id"]
    # find the next date that's a Mon-Sat (the days we set as open)
    d = dt.datetime.utcnow().date() + dt.timedelta(days=1)
    while d.weekday() == 6:  # skip Sunday (closed)
        d += dt.timedelta(days=1)
    slots = client.get(
        "/book/sharma-hair-studio/slots",
        params={"service_id": sid, "date": d.isoformat()},
    ).json()["slots"]
    assert len(slots) > 0


def test_setup_service_delete(client):
    _web_signup(client)
    client.post("/setup/business", data={"name": "Salon"})
    client.post("/setup/services", data={"name": "Cut", "duration_mins": 30, "price": 1})
    # add a second so delete is meaningful (free plan allows 1, so delete the first)
    r = client.post("/setup/services/" + _first_service_id(client) + "/delete")
    assert r.status_code == 200 and "No services yet" in r.text


def _first_service_id(client):
    info = client.get("/book/salon").json()
    return info["services"][0]["id"]
