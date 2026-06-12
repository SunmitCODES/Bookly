from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.schemas.auth import SignupRequest, LoginRequest, TokenResponse, UserOut
from app.services.auth import hash_password, verify_password, create_access_token
from app.config import settings
from app.templating import templates

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Separate router (no /auth prefix) for the browser-facing HTML auth pages.
web_router = APIRouter(tags=["Web Auth"])

_COOKIE_NAME = "access_token"
_COOKIE_MAX_AGE = 60 * 60 * 24 * 7  # 7 days, matches the token expiry


def _set_auth_cookie(response: RedirectResponse, token: str) -> None:
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.environment != "development",
        max_age=_COOKIE_MAX_AGE,
    )

@router.post("/signup", response_model=TokenResponse)
def signup(data: SignupRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    user = User(
        email=data.email,
        hashed_password=hash_password(data.password)
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(str(user.id))
    return {"access_token": token, "token_type": "bearer"}


# ----- Browser-facing HTML auth (cookie-based) -------------------------------

@web_router.get("/login")
def login_page(request: Request, error: str | None = None):
    return templates.TemplateResponse(
        request, "owner/login.html", {"error": error}
    )


@web_router.post("/login")
def login_submit(
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        resp = RedirectResponse(url="/login?error=1", status_code=303)
        return resp
    token = create_access_token(str(user.id))
    resp = RedirectResponse(url="/dashboard", status_code=303)
    _set_auth_cookie(resp, token)
    return resp


@web_router.get("/signup")
def signup_page(request: Request, error: str | None = None):
    return templates.TemplateResponse(
        request, "owner/signup.html", {"error": error}
    )


@web_router.post("/signup")
def signup_submit(
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    if db.query(User).filter(User.email == email).first():
        return RedirectResponse(url="/signup?error=1", status_code=303)
    user = User(email=email, hashed_password=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(str(user.id))
    resp = RedirectResponse(url="/dashboard", status_code=303)
    _set_auth_cookie(resp, token)
    return resp


@web_router.get("/logout")
def logout():
    resp = RedirectResponse(url="/login", status_code=303)
    resp.delete_cookie(_COOKIE_NAME)
    return resp


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    token = create_access_token(str(user.id))
    return {"access_token": token, "token_type": "bearer"}