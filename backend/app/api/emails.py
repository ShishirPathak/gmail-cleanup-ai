from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.email import Email
from app.schemas.email import EmailResponse
from app.services.gmail_service import GmailService
from typing import List

router = APIRouter(prefix="/emails", tags=["emails"])


@router.get("/", response_model=List[EmailResponse])
def list_emails(db: Session = Depends(get_db)):
    emails = db.query(Email).order_by(Email.created_at.desc()).limit(50).all()
    return emails


@router.post("/sync")
def sync_emails(db: Session = Depends(get_db)):
    gmail_service = GmailService()
    items = gmail_service.fetch_recent_emails()

    created = 0

    for item in items:
        existing = db.query(Email).filter(
            Email.gmail_message_id == item["gmail_message_id"]
        ).first()

        if existing:
            continue

        email = Email(
            user_id=1,  # temporary hardcoded user
            gmail_message_id=item["gmail_message_id"],
            gmail_thread_id=item["gmail_thread_id"],
            sender_name=item["sender_name"],
            sender_email=item["sender_email"],
            sender_domain=item["sender_domain"],
            subject=item["subject"],
            snippet=item["snippet"],
            body_text=item["body_text"],
            gmail_labels=item["gmail_labels"],
            has_unsubscribe=item["has_unsubscribe"],
        )
        db.add(email)
        created += 1

    db.commit()

    return {"message": "Sync complete", "created": created}