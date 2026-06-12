import re
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, get_current_business
from app.models.user import User
from app.models.business import Business
from app.schemas.business import BusinessCreate, BusinessUpdate, BusinessOut
from app.services.storage import upload_logo, is_configured, StorageError

router = APIRouter(prefix="/business", tags=["Business"])


def _save_logo(business: Business, file: UploadFile, db: Session) -> Business:
    """Shared upload+validate path for both the API and dashboard routes."""
    if not is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Image storage is not configured.",
        )
    data = file.file.read()
    try:
        url = upload_logo(business.id, data, file.content_type or "")
    except StorageError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    business.logo_url = url
    db.commit()
    db.refresh(business)
    return business


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "business"


def _unique_slug(db: Session, base: str) -> str:
    slug = base
    n = 1
    while db.query(Business).filter(Business.slug == slug).first() is not None:
        n += 1
        slug = f"{base}-{n}"
    return slug


@router.post("", response_model=BusinessOut, status_code=status.HTTP_201_CREATED)
def create_business(
    data: BusinessCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # One business per owner for now.
    existing = (
        db.query(Business).filter(Business.owner_id == current_user.id).first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You already have a business profile.",
        )

    business = Business(
        owner_id=current_user.id,
        name=data.name,
        slug=_unique_slug(db, _slugify(data.name)),
        phone=data.phone,
        address=data.address,
        logo_url=data.logo_url,
    )
    db.add(business)
    db.commit()
    db.refresh(business)
    return business


@router.get("/me", response_model=BusinessOut)
def get_my_business(business: Business = Depends(get_current_business)):
    return business


@router.put("/me", response_model=BusinessOut)
def update_my_business(
    data: BusinessUpdate,
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(business, field, value)
    db.commit()
    db.refresh(business)
    return business


@router.post("/logo", response_model=BusinessOut)
def upload_business_logo(
    file: UploadFile = File(...),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    return _save_logo(business, file, db)
