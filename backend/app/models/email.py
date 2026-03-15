from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.sql import func
from app.db.session import Base


class Email(Base):
    __tablename__ = "emails"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    gmail_message_id = Column(String, unique=True, nullable=False, index=True)
    gmail_thread_id = Column(String, nullable=True, index=True)

    sender_name = Column(String, nullable=True)
    sender_email = Column(String, nullable=True, index=True)
    sender_domain = Column(String, nullable=True, index=True)

    subject = Column(String, nullable=True)
    snippet = Column(Text, nullable=True)
    body_text = Column(Text, nullable=True)

    gmail_labels = Column(Text, nullable=True)
    received_at = Column(DateTime(timezone=True), nullable=True)

    is_read = Column(Boolean, default=False)
    has_unsubscribe = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())