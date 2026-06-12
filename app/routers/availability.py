from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_business
from app.models.business import Business
from app.models.availability import Availability
from app.schemas.availability import AvailabilitySet, AvailabilityOut

router = APIRouter(prefix="/availability", tags=["Availability"])


@router.get("", response_model=list[AvailabilityOut])
def get_availability(
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    return (
        db.query(Availability)
        .filter(Availability.business_id == business.id)
        .order_by(Availability.day_of_week)
        .all()
    )


@router.put("", response_model=list[AvailabilityOut])
def set_availability(
    data: AvailabilitySet,
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    """Replace the entire weekly schedule for this business."""
    db.query(Availability).filter(
        Availability.business_id == business.id
    ).delete()

    rows = [
        Availability(business_id=business.id, **rule.model_dump())
        for rule in data.rules
    ]
    db.add_all(rows)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows
