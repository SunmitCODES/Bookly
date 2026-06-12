from uuid import UUID
from datetime import time
from pydantic import BaseModel, Field


class AvailabilityRule(BaseModel):
    day_of_week: int = Field(ge=0, le=6, description="0=Mon ... 6=Sun")
    start_time: time
    end_time: time
    slot_duration_mins: int = 30
    is_active: bool = True


class AvailabilitySet(BaseModel):
    """Full weekly schedule sent in one PUT — replaces existing rules."""
    rules: list[AvailabilityRule]


class AvailabilityOut(AvailabilityRule):
    id: UUID
    business_id: UUID

    class Config:
        from_attributes = True
