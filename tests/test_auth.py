def test_signup_returns_token(client):
    r = client.post("/auth/signup", json={"email": "a@test.in", "password": "secret123"})
    assert r.status_code == 200
    assert "access_token" in r.json()


def test_login_ok_and_wrong_password(client):
    client.post("/auth/signup", json={"email": "b@test.in", "password": "secret123"})
    ok = client.post("/auth/login", json={"email": "b@test.in", "password": "secret123"})
    assert ok.status_code == 200 and "access_token" in ok.json()
    bad = client.post("/auth/login", json={"email": "b@test.in", "password": "WRONG"})
    assert bad.status_code == 401


def test_duplicate_signup_rejected(client):
    client.post("/auth/signup", json={"email": "c@test.in", "password": "secret123"})
    dup = client.post("/auth/signup", json={"email": "c@test.in", "password": "secret123"})
    assert dup.status_code == 400


def test_web_login_sets_cookie_and_dashboard_guard(client):
    client.post("/auth/signup", json={"email": "d@test.in", "password": "secret123"})
    # no cookie -> dashboard redirects to login
    r = client.get("/dashboard", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
    # web login sets cookie + redirects to dashboard
    r = client.post(
        "/login",
        data={"email": "d@test.in", "password": "secret123"},
        follow_redirects=False,
    )
    assert r.status_code == 303 and r.headers["location"] == "/dashboard"
    assert "access_token" in r.cookies


def test_logout_clears_cookie(client):
    client.post("/auth/signup", json={"email": "e@test.in", "password": "secret123"})
    client.post("/login", data={"email": "e@test.in", "password": "secret123"})
    client.get("/logout")
    r = client.get("/dashboard", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
