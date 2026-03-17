from typing import List
from app.models.user_action import UserAction
from app.schemas.action import UserActionCreate
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.classification import Classification
from app.models.email import Email
from app.schemas.email import EmailResponse
from app.services.gmail_service import GmailService
from app.services.recommendation_service import classify_email

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
        db.flush()

        result = classify_email(
            subject=email.subject,
            snippet=email.snippet,
            labels=email.gmail_labels,
            has_unsubscribe=email.has_unsubscribe,
        )

        classification = Classification(
            email_id=email.id,
            source=result["source"],
            category=result["category"],
            importance=result["importance"],
            suggested_action=result["suggested_action"],
            confidence=result["confidence"],
            reason=result["reason"],
        )
        db.add(classification)

        created += 1

    db.commit()

    return {"message": "Sync complete", "created": created}


@router.get("/classifications")
def list_classifications(db: Session = Depends(get_db)):
    rows = db.query(Classification).order_by(Classification.created_at.desc()).all()
    return [
        {
            "id": row.id,
            "email_id": row.email_id,
            "source": row.source,
            "category": row.category,
            "importance": row.importance,
            "suggested_action": row.suggested_action,
            "confidence": row.confidence,
            "reason": row.reason,
        }
        for row in rows
    ]


@router.get("/{email_id}")
def get_email_detail(email_id: int, db: Session = Depends(get_db)):
    email = db.query(Email).filter(Email.id == email_id).first()
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    classification = (
        db.query(Classification)
        .filter(Classification.email_id == email.id)
        .order_by(Classification.created_at.desc())
        .first()
    )

    actions = (
        db.query(UserAction)
        .filter(UserAction.email_id == email.id)
        .order_by(UserAction.created_at.desc())
        .all()
    )

    return {
        "id": email.id,
        "gmail_message_id": email.gmail_message_id,
        "sender_name": email.sender_name,
        "sender_email": email.sender_email,
        "sender_domain": email.sender_domain,
        "subject": email.subject,
        "snippet": email.snippet,
        "body_text": email.body_text,
        "gmail_labels": email.gmail_labels,
        "has_unsubscribe": email.has_unsubscribe,
        "classification": (
            {
                "category": classification.category,
                "importance": classification.importance,
                "suggested_action": classification.suggested_action,
                "confidence": classification.confidence,
                "reason": classification.reason,
            }
            if classification
            else None
        ),
        "actions": [
            {
                "id": action.id,
                "action_taken": action.action_taken,
                "action_source": action.action_source,
                "created_at": action.created_at,
            }
            for action in actions
        ],
    }

@router.post("/{email_id}/actions")
def add_user_action(
    email_id: int,
    payload: UserActionCreate,
    db: Session = Depends(get_db),
):
    email = db.query(Email).filter(Email.id == email_id).first()
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    action = UserAction(
        user_id=1,  # temporary hardcoded user
        email_id=email_id,
        action_taken=payload.action_taken,
        action_source=payload.action_source,
    )
    db.add(action)
    db.commit()
    db.refresh(action)

    return {
        "id": action.id,
        "email_id": action.email_id,
        "user_id": action.user_id,
        "action_taken": action.action_taken,
        "action_source": action.action_source,
        "created_at": action.created_at,
    }


@router.get("/{email_id}/actions")
def list_email_actions(email_id: int, db: Session = Depends(get_db)):
    email = db.query(Email).filter(Email.id == email_id).first()
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    actions = (
        db.query(UserAction)
        .filter(UserAction.email_id == email_id)
        .order_by(UserAction.created_at.desc())
        .all()
    )

    return [
        {
            "id": action.id,
            "email_id": action.email_id,
            "user_id": action.user_id,
            "action_taken": action.action_taken,
            "action_source": action.action_source,
            "created_at": action.created_at,
        }
        for action in actions
    ]