from uuid import UUID
from pydantic import BaseModel


class BusinessCreate(BaseModel):
    name: str
    phone: str | None = None
    address: str | None = None
    logo_url: str | None = None


class BusinessUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    address: str | None = None
    logo_url: str | None = None


class BusinessOut(BaseModel):
    id: UUID
    name: str
    slug: str
    phone: str | None = None
    address: str | None = None
    logo_url: str | None = None
    plan: str
    plan_status: str

    class Config:
        from_attributes = True
