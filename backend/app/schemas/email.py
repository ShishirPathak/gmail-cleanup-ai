from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class EmailResponse(BaseModel):
    id: int
    gmail_message_id: str
    sender_name: Optional[str] = None
    sender_email: Optional[str] = None
    subject: Optional[str] = None
    snippet: Optional[str] = None
    received_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    is_read: Optional[bool] = None
    has_unsubscribe: bool

    class Config:
        from_attributes = True
