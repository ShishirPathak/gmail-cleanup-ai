from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.email import Email
from app.services.llm_service import LLMService
from app.services.recommendation_policy import (
    classify_email,
    evaluate_risk_flags,
    summarize_similar_actions,
)
from app.services.similarity_service import SimilarityService


class RecommendationService:
    def __init__(self, db: Session):
        self.db = db
        self.similarity_service = SimilarityService(db)
        self.llm_service = LLMService()

    def classify_with_context(
        self,
        *,
        email: Email,
        embedding: list[float],
    ) -> tuple[dict, list[dict]]:
        base = classify_email(
            sender_email=email.sender_email,
            sender_domain=email.sender_domain,
            subject=email.subject,
            snippet=email.snippet,
            labels=email.gmail_labels,
            has_unsubscribe=email.has_unsubscribe,
        )
        similar_rows = self.similarity_service.find_similar_emails(
            user_id=email.user_id,
            email_id=email.id,
            embedding=embedding,
            limit=settings.similarity_limit_default,
        )

        recommended_action, count = summarize_similar_actions(similar_rows)
        result = dict(base)

        if recommended_action and count >= 2 and result["confidence"] < 0.9:
            result["source"] = "hybrid"
            result["suggested_action"] = recommended_action
            result["confidence"] = max(result["confidence"], 0.72)
            result["reason"] = (
                f"{result['reason']}; {count} similar emails had last action '{recommended_action}'"
            )

        if result["confidence"] < 0.55 and self.llm_service.is_enabled():
            try:
                llm_result = self.llm_service.classify_email(
                    sender_email=email.sender_email,
                    sender_domain=email.sender_domain,
                    subject=email.subject,
                    snippet=email.snippet,
                    labels=email.gmail_labels,
                    has_unsubscribe=email.has_unsubscribe,
                )
            except Exception:
                llm_result = None
            if llm_result:
                result.update(
                    {
                        "source": "llm",
                        "category": llm_result.get("category", result["category"]),
                        "importance": llm_result.get("importance", result["importance"]),
                        "suggested_action": llm_result.get(
                            "suggested_action", result["suggested_action"]
                        ),
                        "confidence": float(llm_result.get("confidence", result["confidence"])),
                        "reason": llm_result.get("reason", result["reason"]),
                    }
                )

        risk_flags = evaluate_risk_flags(
            sender_email=email.sender_email,
            sender_domain=email.sender_domain,
            subject=email.subject,
            snippet=email.snippet,
        )
        if risk_flags and result["suggested_action"] in {"archive", "trash"}:
            result["source"] = "hybrid"
            result["category"] = "important"
            result["importance"] = "high"
            result["suggested_action"] = "keep"
            result["confidence"] = max(float(result["confidence"]), 0.95)
            result["reason"] = "guardrail override because " + ", ".join(risk_flags)

        result["risk_flags"] = risk_flags
        return result, similar_rows
