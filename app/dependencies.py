from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.business import Business
from app.services.auth import decode_token


class _RedirectToLogin(Exception):
    """Raised by web auth deps when no valid session cookie is present."""


class _RedirectToSetup(Exception):
    """Raised when a logged-in owner has no business yet — go create one."""

# tokenUrl is just the path the /docs "Authorize" button posts to.
# Our login takes JSON, but this still lets /docs hold the bearer token.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

_credentials_error = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the logged-in User from the Bearer token, or raise 401."""
    user_id = decode_token(token)
    if user_id is None:
        raise _credentials_error
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise _credentials_error
    return user


def get_current_business(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Business:
    """Return the business owned by the current user, or 404 if none yet.

    Reused by services and availability routes so every owner-scoped
    operation runs against the caller's own business automatically.
    """
    business = (
        db.query(Business).filter(Business.owner_id == current_user.id).first()
    )
    if business is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No business found. Create your business profile first.",
        )
    return business


# ----- Cookie-based auth for browser-rendered HTML pages ---------------------

def get_current_user_web(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """Resolve the user from the `access_token` cookie.

    Raises _RedirectToLogin (handled by an exception handler in main.py)
    instead of a 401, so unauthenticated browser visits go to /login.
    """
    token = request.cookies.get("access_token")
    if not token:
        raise _RedirectToLogin()
    user_id = decode_token(token)
    if user_id is None:
        raise _RedirectToLogin()
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise _RedirectToLogin()
    return user


def get_current_business_web(
    current_user: User = Depends(get_current_user_web),
    db: Session = Depends(get_db),
) -> Business:
    business = (
        db.query(Business).filter(Business.owner_id == current_user.id).first()
    )
    if business is None:
        # logged in but no business yet — send them to the setup page
        raise _RedirectToSetup()
    return business
