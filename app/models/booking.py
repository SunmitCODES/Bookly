import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Boolean
from app.db_types import GUID
from sqlalchemy.orm import relationship
from app.database import Base

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    business_id = Column(GUID(), ForeignKey("businesses.id"), nullable=False)
    service_id = Column(GUID(), ForeignKey("services.id"), nullable=False)
    customer_name = Column(String, nullable=False)
    customer_phone = Column(String, nullable=False)
    customer_email = Column(String)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    status = Column(String, default="confirmed")
    manage_token = Column(String, unique=True, index=True, nullable=True)
    reminder_sent = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    business = relationship("Business", backref="bookings")
    service = relationship("Service", backref="bookings")