from pydantic import BaseModel, Field


class UserActionCreate(BaseModel):
    action_taken: str = Field(..., pattern="^(keep|archive|delete)$")
    action_source: str = Field(default="manual", pattern="^(manual|auto)$")