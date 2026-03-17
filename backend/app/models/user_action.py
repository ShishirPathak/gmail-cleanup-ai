from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.sql import func
from app.db.session import Base


class UserAction(Base):
    __tablename__ = "user_actions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    email_id = Column(Integer, ForeignKey("emails.id"), nullable=False)

    action_taken = Column(String, nullable=False)  # keep / archive / trash / mark_read / label
    action_source = Column(String, nullable=False, default="manual")  # manual / auto

    created_at = Column(DateTime(timezone=True), server_default=func.now())
