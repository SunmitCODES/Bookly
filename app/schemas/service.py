from uuid import UUID
from pydantic import BaseModel

class ServiceCreate(BaseModel):
    name: str
    duration_mins: int
    price: float
    description: str = ""

class ServiceUpdate(BaseModel):
    name: str | None = None
    duration_mins: int | None = None
    price: float | None = None
    description: str | None = None

class ServiceOut(ServiceCreate):
    id: UUID
    business_id: UUID

    class Config:
        from_attributes = True