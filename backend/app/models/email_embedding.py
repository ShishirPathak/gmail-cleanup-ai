from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector

from app.db.session import Base


class EmailEmbedding(Base):
    __tablename__ = "email_embeddings"

    id = Column(Integer, primary_key=True, index=True)
    email_id = Column(Integer, ForeignKey("emails.id"), nullable=False, unique=True)
    model_name = Column(String, nullable=False)
    embedding = Column(Vector(), nullable=False)
    embedded_at = Column(DateTime(timezone=True), server_default=func.now())
