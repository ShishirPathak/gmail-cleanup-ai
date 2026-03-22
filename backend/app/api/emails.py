from typing import List
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.redis import redis_client
from app.db.session import get_db
from app.models.classification import Classification
from app.models.email import Email
from app.models.email_embedding import EmailEmbedding
from app.models.user import User
from app.models.user_action import UserAction
from app.schemas.action import BulkArchiveRequest, CleanupActionRequest, UserActionCreate
from app.schemas.email import EmailResponse
from app.services.account_service import AccountService
from app.services.embedding_service import EmbeddingService, FakeEmbeddingProvider, build_embedding_text
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
        .filter(
            Email.user_id == current_user.id,
            _email_is_in_inbox(),
        )
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


@router.post("/dev-seed")
def seed_demo_emails(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if settings.environment.lower() == "production":
        raise HTTPException(status_code=404, detail="Not found")

    demo_email_ids = [
        row[0]
        for row in db.query(Email.id)
        .filter(
            Email.user_id == current_user.id,
            Email.gmail_message_id.like("demo-%"),
        )
        .all()
    ]
    if demo_email_ids:
        db.query(UserAction).filter(UserAction.email_id.in_(demo_email_ids)).delete(
            synchronize_session=False
        )
        db.query(Classification).filter(Classification.email_id.in_(demo_email_ids)).delete(
            synchronize_session=False
        )
        db.query(EmailEmbedding).filter(EmailEmbedding.email_id.in_(demo_email_ids)).delete(
            synchronize_session=False
        )
        db.query(Email).filter(Email.id.in_(demo_email_ids)).delete(synchronize_session=False)
        db.commit()

    now = datetime.now(timezone.utc)
    samples = [
        {
            "sender_name": "Acme Alerts",
            "sender_email": "security@accounts.acme.com",
            "sender_domain": "accounts.acme.com",
            "subject": "Your verification code is 482193",
            "snippet": "Use this code to complete your sign in.",
            "body_text": "We noticed a login attempt. Use code 482193 to continue.",
            "gmail_labels": "INBOX,IMPORTANT",
            "gmail_label_ids": "INBOX,IMPORTANT",
            "has_unsubscribe": False,
            "is_read": False,
            "received_at": now - timedelta(minutes=12),
        },
        {
            "sender_name": "Studio Weekly",
            "sender_email": "news@studio-weekly.demo",
            "sender_domain": "studio-weekly.demo",
            "subject": "This week in product design",
            "snippet": "Fresh articles, community links, and a short workshop invite.",
            "body_text": "A short curated roundup from the design community. Read the latest stories and resources.",
            "gmail_labels": "INBOX,UPDATES",
            "gmail_label_ids": "INBOX,UPDATES",
            "has_unsubscribe": False,
            "is_read": False,
            "received_at": now - timedelta(hours=3),
        },
        {
            "sender_name": "Nimbus",
            "sender_email": "hello@nimbus-app.demo",
            "sender_domain": "nimbus-app.demo",
            "subject": "Your team workspace digest",
            "snippet": "A quick summary of this week's comments, mentions, and next steps.",
            "body_text": "Here is a summary of recent work across your team. There are comments, mentions, and project updates to review.",
            "gmail_labels": "INBOX",
            "gmail_label_ids": "INBOX",
            "has_unsubscribe": False,
            "is_read": False,
            "received_at": now - timedelta(hours=7),
        },
        {
            "sender_name": "MarketLane",
            "sender_email": "offers@marketlane.demo",
            "sender_domain": "marketlane.demo",
            "subject": "Weekend sale just started",
            "snippet": "Members save 25% today only. Limited time offer.",
            "body_text": "Exclusive member sale. Shop now and save 25 percent today only.",
            "gmail_labels": "INBOX,PROMOTIONS",
            "gmail_label_ids": "INBOX,PROMOTIONS",
            "has_unsubscribe": True,
            "is_read": False,
            "received_at": now - timedelta(days=1),
        },
    ]

    embedding_service = EmbeddingService()
    recommendation_service = RecommendationService(db)
    created = []
    used_fallback_embeddings = False

    for sample in samples:
        email = Email(
            user_id=current_user.id,
            gmail_message_id=f"demo-{uuid4()}",
            gmail_thread_id=f"demo-thread-{uuid4()}",
            **sample,
        )
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
        try:
            embedding_result = embedding_service.embed_text(embedding_text)
        except Exception:
            embedding_service = EmbeddingService(provider=FakeEmbeddingProvider())
            embedding_result = embedding_service.embed_text(embedding_text)
            used_fallback_embeddings = True
        db.add(
            EmailEmbedding(
                email_id=email.id,
                model_name=embedding_result.model_name,
                embedding=embedding_result.vector,
            )
        )

        recommendation, _ = recommendation_service.classify_with_context(
            email=email,
            embedding=embedding_result.vector,
        )
        db.add(
            Classification(
                email_id=email.id,
                source=recommendation["source"],
                category=recommendation["category"],
                importance=recommendation["importance"],
                suggested_action=recommendation["suggested_action"],
                confidence=recommendation["confidence"],
                reason=recommendation["reason"],
            )
        )
        created.append(
            {
                "id": email.id,
                "subject": email.subject,
                "source": recommendation["source"],
                "action": recommendation["suggested_action"],
            }
        )

    db.commit()
    return {
        "message": "Demo inbox seeded",
        "count": len(created),
        "emails": created,
        "used_fallback_embeddings": used_fallback_embeddings,
    }


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


@router.get("/archive-candidates")
def list_archive_candidates(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    emails = (
        db.query(Email)
        .filter(
            Email.user_id == current_user.id,
            _email_is_in_inbox(),
        )
        .order_by(Email.received_at.desc().nullslast(), Email.created_at.desc())
        .limit(100)
        .all()
    )

    candidates = []
    for email in emails:
        classification = _get_latest_classification(db, email.id)
        if not classification or classification.suggested_action != "archive":
            continue

        risk_flags = evaluate_risk_flags(
            sender_email=email.sender_email,
            sender_domain=email.sender_domain,
            subject=email.subject,
            snippet=email.snippet,
        )
        if risk_flags:
            continue

        candidates.append(
            {
                "id": email.id,
                "sender_name": email.sender_name,
                "sender_email": email.sender_email,
                "subject": email.subject,
                "snippet": email.snippet,
                "received_at": email.received_at,
                "created_at": email.created_at,
                "classification": {
                    "source": classification.source,
                    "category": classification.category,
                    "importance": classification.importance,
                    "suggested_action": classification.suggested_action,
                    "confidence": classification.confidence,
                    "reason": classification.reason,
                },
            }
        )

    return {"count": len(candidates), "emails": candidates}


@router.post("/archive-candidates/archive")
def archive_reviewed_candidates(
    payload: BulkArchiveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    account = AccountService(db).get_primary_account(current_user.id)
    if not account and not _all_demo_emails(db, current_user, payload.email_ids):
        raise HTTPException(status_code=400, detail="Connect a Gmail account first")

    if not payload.email_ids:
        raise HTTPException(status_code=400, detail="email_ids is required")

    gmail_service = GmailService(db) if account else None
    archived = []
    skipped = []

    for email_id in payload.email_ids:
        email = _get_owned_email(db, current_user, email_id)
        if not email or not _has_inbox_label(email.gmail_labels):
            skipped.append({"email_id": email_id, "reason": "Email not available in inbox"})
            continue

        classification = _get_latest_classification(db, email.id)
        if not classification or classification.suggested_action != "archive":
            skipped.append({"email_id": email.id, "reason": "Latest recommendation is not archive"})
            continue

        risk_flags = evaluate_risk_flags(
            sender_email=email.sender_email,
            sender_domain=email.sender_domain,
            subject=email.subject,
            snippet=email.snippet,
        )
        if risk_flags:
            skipped.append({"email_id": email.id, "reason": "Email is high risk"})
            continue

        if account:
            gmail_service.archive_message(account, email.gmail_message_id)
        email.gmail_labels = _remove_label(email.gmail_labels, "INBOX")
        email.gmail_label_ids = _remove_label(email.gmail_label_ids, "INBOX")
        db.add(
            UserAction(
                user_id=current_user.id,
                email_id=email.id,
                action_taken="archive",
                action_source="manual",
            )
        )
        archived.append(email.id)

    db.commit()
    return {"archived_count": len(archived), "archived_email_ids": archived, "skipped": skipped}


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
        "received_at": email.received_at,
        "created_at": email.created_at,
        "risk_flags": evaluate_risk_flags(
            sender_email=email.sender_email,
            sender_domain=email.sender_domain,
            subject=email.subject,
            snippet=email.snippet,
        ),
        "classification": (
            {
                "source": classification.source,
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
    is_demo_email = _is_demo_email(email)
    if not account and not is_demo_email:
        raise HTTPException(status_code=400, detail="Connect a Gmail account first")

    latest_classification = _get_latest_classification(db, email.id)
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

    gmail_service = GmailService(db) if account else None
    if payload.action == "archive":
        if account:
            gmail_service.archive_message(account, email.gmail_message_id)
        email.gmail_labels = _remove_label(email.gmail_labels, "INBOX")
        email.gmail_label_ids = _remove_label(email.gmail_label_ids, "INBOX")
    elif payload.action == "trash":
        if account:
            gmail_service.trash_message(account, email.gmail_message_id)
        email.gmail_labels = _add_label(_remove_label(email.gmail_labels, "INBOX"), "TRASH")
        email.gmail_label_ids = _add_label(_remove_label(email.gmail_label_ids, "INBOX"), "TRASH")
    elif payload.action == "mark_read":
        if account:
            gmail_service.mark_as_read(account, email.gmail_message_id)
        email.is_read = True
        email.gmail_labels = _remove_label(email.gmail_labels, "UNREAD")
        email.gmail_label_ids = _remove_label(email.gmail_label_ids, "UNREAD")
    elif payload.action == "label":
        if not payload.label_names:
            raise HTTPException(status_code=400, detail="label_names is required for label action")
        if account:
            label_ids = gmail_service.apply_labels(
                account,
                email.gmail_message_id,
                payload.label_names,
            )
            existing = set((email.gmail_label_ids or "").split(",")) if email.gmail_label_ids else set()
            email.gmail_label_ids = ",".join(sorted(existing.union(label_ids)))
        else:
            existing_ids = set((email.gmail_label_ids or "").split(",")) if email.gmail_label_ids else set()
            existing_names = set((email.gmail_labels or "").split(",")) if email.gmail_labels else set()
            email.gmail_label_ids = ",".join(sorted(existing_ids.union(payload.label_names)))
            email.gmail_labels = ",".join(sorted(existing_names.union(payload.label_names)))
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


def _get_latest_classification(db: Session, email_id: int) -> Classification | None:
    return (
        db.query(Classification)
        .filter(Classification.email_id == email_id)
        .order_by(Classification.created_at.desc())
        .first()
    )


def _email_is_in_inbox():
    return or_(
        Email.gmail_labels == "INBOX",
        Email.gmail_labels.like("INBOX,%"),
        Email.gmail_labels.like("%,INBOX"),
        Email.gmail_labels.like("%,INBOX,%"),
    )


def _has_inbox_label(value: str | None) -> bool:
    if not value:
        return False
    labels = {item.strip() for item in value.split(",") if item.strip()}
    return "INBOX" in labels


def _is_demo_email(email: Email) -> bool:
    return bool(email.gmail_message_id and email.gmail_message_id.startswith("demo-"))


def _all_demo_emails(db: Session, current_user: User, email_ids: list[int]) -> bool:
    if not email_ids:
        return False
    emails = (
        db.query(Email)
        .filter(Email.user_id == current_user.id, Email.id.in_(email_ids))
        .all()
    )
    return len(emails) == len(email_ids) and all(_is_demo_email(email) for email in emails)


def _remove_label(value: str | None, label: str) -> str | None:
    if not value:
        return None
    labels = [item.strip() for item in value.split(",") if item.strip() and item.strip() != label]
    return ",".join(labels) if labels else None


def _add_label(value: str | None, label: str) -> str:
    labels = [item.strip() for item in (value or "").split(",") if item.strip()]
    if label not in labels:
        labels.append(label)
    return ",".join(labels)
