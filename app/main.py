from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from app.config import settings
from app.routers import auth, business, services, availability, bookings, pages, payments
from app.dependencies import _RedirectToLogin, _RedirectToSetup
from app.templating import templates
from app.database import Base, engine

# Initialise Sentry error monitoring only when a DSN is configured.
if settings.sentry_dsn:
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        traces_sample_rate=0.1,
    )
# Import model modules so their tables register on Base before create_all.
# Aliased to avoid clashing with the router module names above.
from app.models import (
    user as _m_user,
    business as _m_business,
    service as _m_service,
    booking as _m_booking,
    availability as _m_availability,
)

# Skip auto-create under pytest — tests build their own isolated schema
# (see tests/conftest.py) and shouldn't create a stray bookly.db on import.
import sys as _sys

if "pytest" not in _sys.modules:
    # Don't let a transient DB hiccup crash startup (and fail the healthcheck).
    # Log it and continue; the next request will reconnect.
    import logging as _logging

    try:
        Base.metadata.create_all(bind=engine)
    except Exception as _exc:  # noqa: BLE001
        _logging.getLogger("bookly").error(
            "create_all failed at startup (continuing): %s", _exc
        )

app = FastAPI(
    title="Bookly",
    description="Appointment booking SaaS",
    version="0.1.0"
)

app.mount("/static", StaticFiles(directory="static"), name="static")


# Web auth deps raise this when no valid session cookie is present —
# send the browser to the login page instead of returning a JSON 401.
@app.exception_handler(_RedirectToLogin)
async def _redirect_to_login(request: Request, exc: _RedirectToLogin):
    return RedirectResponse(url="/login", status_code=303)


@app.exception_handler(_RedirectToSetup)
async def _redirect_to_setup(request: Request, exc: _RedirectToSetup):
    return RedirectResponse(url="/setup/business", status_code=303)


app.include_router(auth.router)
app.include_router(auth.web_router)
app.include_router(business.router)
app.include_router(services.router)
app.include_router(availability.router)
app.include_router(bookings.router)
app.include_router(payments.router)
# Pages last: /b/{slug} is greedy, register after the API routers.
app.include_router(pages.router)

@app.get("/")
def root():
    return {"message": "Bookly API is running!"}

@app.get("/health")
def health_check():
    return {"status": "ok"}