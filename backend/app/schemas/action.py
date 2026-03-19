from typing import List

from pydantic import BaseModel, Field


class UserActionCreate(BaseModel):
    action_taken: str = Field(
        ...,
        pattern="^(keep|archive|trash|mark_read|label|review)$",
    )
    action_source: str = Field(default="manual", pattern="^(manual|auto)$")


class CleanupActionRequest(BaseModel):
    action: str = Field(..., pattern="^(archive|trash|mark_read|label)$")
    label_names: List[str] = Field(default_factory=list)
    confirm_high_risk: bool = False
