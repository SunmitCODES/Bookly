import uuid
from sqlalchemy import Column, Integer, Time, ForeignKey, Boolean
from app.db_types import GUID
from sqlalchemy.orm import relationship
from app.database import Base

class Availability(Base):
    __tablename__ = "availability"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    business_id = Column(GUID(), ForeignKey("businesses.id"), nullable=False)
    day_of_week = Column(Integer, nullable=False)  # 0=Mon, 6=Sun
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    slot_duration_mins = Column(Integer, default=30)
    is_active = Column(Boolean, default=True)

    business = relationship("Business", backref="availability")