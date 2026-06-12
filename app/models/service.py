import uuid
from sqlalchemy import Column, String, Integer, Numeric, Text, ForeignKey
from app.db_types import GUID
from sqlalchemy.orm import relationship
from app.database import Base

class Service(Base):
    __tablename__ = "services"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    business_id = Column(GUID(), ForeignKey("businesses.id"), nullable=False)
    name = Column(String, nullable=False)
    duration_mins = Column(Integer, nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    description = Column(Text, default="")

    business = relationship("Business", backref="services")