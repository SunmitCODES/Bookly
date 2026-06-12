import io

import pytest


@pytest.fixture
def r2_configured(monkeypatch):
    """Configure R2 settings + mock the S3 client; record put_object calls."""
    from app.config import settings
    import app.services.storage as storage

    monkeypatch.setattr(settings, "r2_account_id", "acct")
    monkeypatch.setattr(settings, "r2_access_key_id", "ak")
    monkeypatch.setattr(settings, "r2_secret_access_key", "sk")
    monkeypatch.setattr(settings, "r2_bucket", "bookly-logos")
    monkeypatch.setattr(settings, "r2_public_base_url", "https://pub-test.r2.dev")

    calls = []

    class FakeS3:
        def put_object(self, **kw):
            calls.append(kw)

    monkeypatch.setattr(storage, "_s3_client", lambda: FakeS3())
    return calls


PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100


def test_upload_happy_path(client, shop, r2_configured):
    r = client.post(
        "/business/logo",
        headers=shop["headers"],
        files={"file": ("logo.png", io.BytesIO(PNG), "image/png")},
    )
    assert r.status_code == 200
    assert r.json()["logo_url"].startswith("https://pub-test.r2.dev/logos/")
    assert len(r2_configured) == 1
    assert r2_configured[0]["Bucket"] == "bookly-logos"
    assert r2_configured[0]["ContentType"] == "image/png"


def test_reject_bad_type(client, shop, r2_configured):
    r = client.post(
        "/business/logo",
        headers=shop["headers"],
        files={"file": ("x.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert r.status_code == 400
    assert len(r2_configured) == 0


def test_reject_oversized(client, shop, r2_configured):
    big = b"0" * (3 * 1024 * 1024)
    r = client.post(
        "/business/logo",
        headers=shop["headers"],
        files={"file": ("big.png", io.BytesIO(big), "image/png")},
    )
    assert r.status_code == 400


def test_unconfigured_returns_503(client, shop):
    # r2_configured fixture NOT used -> storage blank -> 503
    r = client.post(
        "/business/logo",
        headers=shop["headers"],
        files={"file": ("logo.png", io.BytesIO(PNG), "image/png")},
    )
    assert r.status_code == 503


def test_public_page_shows_logo(client, shop, r2_configured):
    client.post(
        "/business/logo",
        headers=shop["headers"],
        files={"file": ("logo.png", io.BytesIO(PNG), "image/png")},
    )
    r = client.get(f"/b/{shop['slug']}")
    assert "pub-test.r2.dev" in r.text
