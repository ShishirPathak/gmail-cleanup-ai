from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Text
from sqlalchemy.sql import func
from app.db.session import Base


class Classification(Base):
    __tablename__ = "classifications"

    id = Column(Integer, primary_key=True, index=True)
    email_id = Column(Integer, ForeignKey("emails.id"), nullable=False)

    source = Column(String, nullable=False)  # rule / llm / hybrid
    category = Column(String, nullable=True)
    importance = Column(String, nullable=True)
    suggested_action = Column(String, nullable=True)  # keep / archive / delete / review
    confidence = Column(Float, nullable=True)
    reason = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())