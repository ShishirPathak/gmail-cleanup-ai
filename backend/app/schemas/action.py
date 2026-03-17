from pydantic import BaseModel, Field


class UserActionCreate(BaseModel):
    action_taken: str = Field(
        ...,
        pattern="^(keep|archive|trash|mark_read|label|review)$",
    )
    action_source: str = Field(default="manual", pattern="^(manual|auto)$")
