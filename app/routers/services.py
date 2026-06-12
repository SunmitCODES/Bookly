from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_business
from app.models.business import Business
from app.models.service import Service
from app.schemas.service import ServiceCreate, ServiceUpdate, ServiceOut
from app.services.billing import can_add_service

router = APIRouter(prefix="/services", tags=["Services"])


def _get_owned_service(service_id: UUID, business: Business, db: Session) -> Service:
    service = (
        db.query(Service)
        .filter(Service.id == service_id, Service.business_id == business.id)
        .first()
    )
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found.",
        )
    return service


@router.post("", response_model=ServiceOut, status_code=status.HTTP_201_CREATED)
def create_service(
    data: ServiceCreate,
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    ok, reason = can_add_service(db, business)
    if not ok:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=reason)
    service = Service(business_id=business.id, **data.model_dump())
    db.add(service)
    db.commit()
    db.refresh(service)
    return service


@router.get("", response_model=list[ServiceOut])
def list_services(
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    return db.query(Service).filter(Service.business_id == business.id).all()


@router.put("/{service_id}", response_model=ServiceOut)
def update_service(
    service_id: UUID,
    data: ServiceUpdate,
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    service = _get_owned_service(service_id, business, db)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(service, field, value)
    db.commit()
    db.refresh(service)
    return service


@router.delete("/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_service(
    service_id: UUID,
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    service = _get_owned_service(service_id, business, db)
    db.delete(service)
    db.commit()
    return None
