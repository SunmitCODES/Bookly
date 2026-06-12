from uuid import UUID
from datetime import datetime
from pydantic import BaseModel

class BookingCreate(BaseModel):
    service_id: UUID
    customer_name: str
    customer_phone: str
    customer_email: str = ""
    start_time: datetime

class BookingOut(BaseModel):
    id: UUID
    customer_name: str
    customer_phone: str
    start_time: datetime
    end_time: datetime
    status: str

    class Config:
        from_attributes = True


class PublicServiceOut(BaseModel):
    id: UUID
    name: str
    duration_mins: int
    price: float
    description: str = ""

    class Config:
        from_attributes = True


class PublicBusinessOut(BaseModel):
    name: str
    slug: str
    phone: str | None = None
    address: str | None = None
    logo_url: str | None = None
    services: list[PublicServiceOut]


class SlotsOut(BaseModel):
    date: str
    service_id: UUID
    slots: list[datetime]