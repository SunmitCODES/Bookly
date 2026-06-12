def test_create_and_get_business(client, owner_token):
    r = client.post("/business", json={"name": "Glamour Salon & Spa"}, headers=owner_token)
    assert r.status_code == 201
    body = r.json()
    assert body["slug"] == "glamour-salon-spa"
    assert body["plan"] == "free"
    assert client.get("/business/me", headers=owner_token).status_code == 200


def test_one_business_per_owner(client, owner_token):
    client.post("/business", json={"name": "First"}, headers=owner_token)
    dup = client.post("/business", json={"name": "Second"}, headers=owner_token)
    assert dup.status_code == 400


def test_update_business(client, owner_token):
    client.post("/business", json={"name": "Salon"}, headers=owner_token)
    r = client.put("/business/me", json={"address": "MG Road"}, headers=owner_token)
    assert r.status_code == 200 and r.json()["address"] == "MG Road"


def test_services_crud(client, shop):
    h = shop["headers"]
    assert len(client.get("/services", headers=h).json()) == 1  # from fixture
    sid = shop["service_id"]
    edited = client.put(f"/services/{sid}", json={"price": 349}, headers=h)
    assert edited.json()["price"] == 349
    assert client.delete(f"/services/{sid}", headers=h).status_code == 204
    assert len(client.get("/services", headers=h).json()) == 0


def test_unauthenticated_blocked(client):
    assert client.get("/business/me").status_code == 401
    assert client.get("/services").status_code == 401


def test_cross_owner_service_isolation(client, shop):
    # second owner cannot touch first owner's service
    client.post("/auth/signup", json={"email": "o2@test.in", "password": "secret123"})
    tok2 = client.post(
        "/auth/login", json={"email": "o2@test.in", "password": "secret123"}
    ).json()["access_token"]
    h2 = {"Authorization": f"Bearer {tok2}"}
    client.post("/business", json={"name": "Other"}, headers=h2)
    r = client.put(f"/services/{shop['service_id']}", json={"price": 1}, headers=h2)
    assert r.status_code == 404


def test_availability_set_and_get(client, shop):
    h = shop["headers"]
    rules = client.get("/availability", headers=h).json()
    assert len(rules) == 7  # fixture set all 7 days
