from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.redis import redis_client
from app.db.session import get_db
from app.models.classification import Classification
from app.models.email import Email
from app.models.email_embedding import EmailEmbedding
from app.models.user import User
from app.models.user_action import UserAction
from app.schemas.action import CleanupActionRequest, UserActionCreate
from app.schemas.email import EmailResponse
from app.services.account_service import AccountService
from app.services.embedding_service import EmbeddingService, build_embedding_text
from app.services.gmail_service import GmailService
from app.services.recommendation_policy import evaluate_risk_flags
from app.services.recommendation_service import RecommendationService
from app.services.similarity_service import SimilarityService

router = APIRouter(prefix="/emails", tags=["emails"])


@router.get("/", response_model=List[EmailResponse])
def list_emails(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    emails = (
        db.query(Email)
        .filter(Email.user_id == current_user.id)
        .order_by(Email.received_at.desc().nullslast(), Email.created_at.desc())
        .limit(50)
        .all()
    )
    return emails


@router.post("/sync")
def sync_emails(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    account = AccountService(db).get_primary_account(current_user.id)
    if not account:
        raise HTTPException(status_code=400, detail="Connect a Gmail account first")

    sync_lock_key = f"sync-lock:{current_user.id}"
    if not redis_client.set(sync_lock_key, "1", ex=300, nx=True):
        raise HTTPException(status_code=409, detail="A sync is already running for this user")

    gmail_service = GmailService(db)
    embedding_service = EmbeddingService()
    recommendation_service = RecommendationService(db)
    try:
        items = gmail_service.sync_recent_emails(user_id=current_user.id, account=account)
        created = 0
        updated = 0

        for item in items:
            existing = db.query(Email).filter(
                Email.user_id == current_user.id,
                Email.gmail_message_id == item.gmail_message_id,
            ).first()

            email = existing or Email(
                user_id=current_user.id,
                gmail_account_id=account.id,
                gmail_message_id=item.gmail_message_id,
            )
            email.gmail_account_id = account.id
            email.gmail_thread_id = item.gmail_thread_id
            email.sender_name = item.sender_name
            email.sender_email = item.sender_email
            email.sender_domain = item.sender_domain
            email.subject = item.subject
            email.snippet = item.snippet
            email.body_text = item.body_text
            email.gmail_labels = item.gmail_labels
            email.gmail_label_ids = item.gmail_label_ids
            email.has_unsubscribe = item.has_unsubscribe
            email.is_read = item.is_read
            email.received_at = item.received_at
            db.add(email)
            db.flush()

            embedding_text = build_embedding_text(
                sender_name=email.sender_name,
                sender_email=email.sender_email,
                sender_domain=email.sender_domain,
                subject=email.subject,
                snippet=email.snippet,
                labels=email.gmail_labels,
                has_unsubscribe=email.has_unsubscribe,
            )
            embedding_result = embedding_service.embed_text(embedding_text)

            email_embedding = EmailEmbedding(
                email_id=email.id,
                model_name=embedding_result.model_name,
                embedding=embedding_result.vector,
            )
            if existing:
                stored_embedding = (
                    db.query(EmailEmbedding)
                    .filter(EmailEmbedding.email_id == email.id)
                    .first()
                )
                if stored_embedding:
                    stored_embedding.model_name = embedding_result.model_name
                    stored_embedding.embedding = embedding_result.vector
                else:
                    db.add(email_embedding)
                updated += 1
            else:
                db.add(email_embedding)
                created += 1

            recommendation, _ = recommendation_service.classify_with_context(
                email=email,
                embedding=embedding_result.vector,
            )
            classification = Classification(
                email_id=email.id,
                source=recommendation["source"],
                category=recommendation["category"],
                importance=recommendation["importance"],
                suggested_action=recommendation["suggested_action"],
                confidence=recommendation["confidence"],
                reason=recommendation["reason"],
            )
            db.add(classification)

        db.commit()
        return {"message": "Sync complete", "created": created, "updated": updated}
    finally:
        redis_client.delete(sync_lock_key)


@router.get("/classifications")
def list_classifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(Classification)
        .join(Email, Email.id == Classification.email_id)
        .filter(Email.user_id == current_user.id)
        .order_by(Classification.created_at.desc())
        .all()
    )
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
def get_email_detail(
    email_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    email = _get_owned_email(db, current_user, email_id)
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

    embedding = (
        db.query(EmailEmbedding)
        .filter(EmailEmbedding.email_id == email.id)
        .first()
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
        "is_read": email.is_read,
        "has_unsubscribe": email.has_unsubscribe,
        "risk_flags": evaluate_risk_flags(
            sender_email=email.sender_email,
            sender_domain=email.sender_domain,
            subject=email.subject,
            snippet=email.snippet,
        ),
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
        "embedding": (
            {
                "id": embedding.id,
                "model_name": embedding.model_name,
                "dimension": len(embedding.embedding),
            }
            if embedding
            else None
        ),
    }

@router.post("/{email_id}/actions")
def add_user_action(
    email_id: int,
    payload: UserActionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    email = _get_owned_email(db, current_user, email_id)
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    action = UserAction(
        user_id=current_user.id,
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


@router.post("/{email_id}/execute")
def execute_cleanup_action(
    email_id: int,
    payload: CleanupActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    email = _get_owned_email(db, current_user, email_id)
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    account = AccountService(db).get_primary_account(current_user.id)
    if not account:
        raise HTTPException(status_code=400, detail="Connect a Gmail account first")

    latest_classification = (
        db.query(Classification)
        .filter(Classification.email_id == email.id)
        .order_by(Classification.created_at.desc())
        .first()
    )
    risk_flags = evaluate_risk_flags(
        sender_email=email.sender_email,
        sender_domain=email.sender_domain,
        subject=email.subject,
        snippet=email.snippet,
    )
    is_high_risk = bool(risk_flags) or (
        latest_classification and latest_classification.importance == "high"
    )
    if (
        payload.action in {"archive", "trash"}
        and is_high_risk
        and not payload.confirm_high_risk
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "message": "High-risk email requires confirm_high_risk=true",
                "risk_flags": risk_flags,
            },
        )

    gmail_service = GmailService(db)
    if payload.action == "archive":
        gmail_service.archive_message(account, email.gmail_message_id)
        if email.gmail_labels:
            email.gmail_labels = ",".join(
                label for label in email.gmail_labels.split(",") if label != "INBOX"
            )
    elif payload.action == "trash":
        gmail_service.trash_message(account, email.gmail_message_id)
    elif payload.action == "mark_read":
        gmail_service.mark_as_read(account, email.gmail_message_id)
        email.is_read = True
    elif payload.action == "label":
        if not payload.label_names:
            raise HTTPException(status_code=400, detail="label_names is required for label action")
        label_ids = gmail_service.apply_labels(
            account,
            email.gmail_message_id,
            payload.label_names,
        )
        existing = set((email.gmail_label_ids or "").split(",")) if email.gmail_label_ids else set()
        email.gmail_label_ids = ",".join(sorted(existing.union(label_ids)))
    else:
        raise HTTPException(status_code=400, detail="Unsupported action")

    user_action = UserAction(
        user_id=current_user.id,
        email_id=email.id,
        action_taken=payload.action,
        action_source="manual",
    )
    db.add(user_action)
    db.commit()
    db.refresh(user_action)

    return {
        "status": "applied",
        "action": payload.action,
        "email_id": email.id,
        "risk_flags": risk_flags,
        "user_action_id": user_action.id,
    }


@router.get("/{email_id}/actions")
def list_email_actions(
    email_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    email = _get_owned_email(db, current_user, email_id)
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

@router.get("/{email_id}/similar")
def get_similar_emails(
    email_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    email = _get_owned_email(db, current_user, email_id)
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    source_embedding = (
        db.query(EmailEmbedding)
        .filter(EmailEmbedding.email_id == email_id)
        .first()
    )
    if not source_embedding:
        raise HTTPException(status_code=404, detail="Embedding not found for email")

    rows = SimilarityService(db).find_similar_emails(
        user_id=current_user.id,
        email_id=email_id,
        embedding=source_embedding.embedding,
    )
    return rows


def _get_owned_email(db: Session, current_user: User, email_id: int) -> Email | None:
    return (
        db.query(Email)
        .filter(Email.id == email_id, Email.user_id == current_user.id)
        .first()
    )
