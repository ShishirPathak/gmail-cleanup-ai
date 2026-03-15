from pydantic import BaseModel
from typing import Optional


class EmailResponse(BaseModel):
    id: int
    gmail_message_id: str
    sender_name: Optional[str] = None
    sender_email: Optional[str] = None
    subject: Optional[str] = None
    snippet: Optional[str] = None
    has_unsubscribe: bool

    class Config:
        from_attributes = True