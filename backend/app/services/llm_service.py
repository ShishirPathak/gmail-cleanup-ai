from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.config import settings

ALLOWED_CATEGORIES = {"important", "promotion", "newsletter", "personal", "work", "unknown"}
ALLOWED_IMPORTANCE = {"high", "medium", "low"}
ALLOWED_ACTIONS = {"keep", "archive", "trash", "review"}


class LLMService:
    def is_enabled(self) -> bool:
        return settings.llm_provider.lower() == "openai" and bool(settings.llm_api_key)

    def classify_email(
        self,
        *,
        sender_email: str | None,
        sender_domain: str | None,
        subject: str | None,
        snippet: str | None,
        labels: str | None,
        has_unsubscribe: bool,
    ) -> dict | None:
        if not self.is_enabled():
            return None

        response = httpx.post(
            f"{settings.llm_base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.llm_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.llm_model,
                "temperature": 0,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "email_classification",
                        "schema": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "category": {"type": "string"},
                                "importance": {"type": "string"},
                                "suggested_action": {"type": "string"},
                                "confidence": {"type": "number"},
                                "reason": {"type": "string"},
                            },
                            "required": [
                                "category",
                                "importance",
                                "suggested_action",
                                "confidence",
                                "reason",
                            ],
                        },
                    },
                },
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You classify Gmail messages for inbox cleanup. "
                            "Be conservative. When uncertain, prefer review over archive or trash. "
                            "Security, finance, travel, hiring, billing, receipts, password resets, and personal correspondence "
                            "must not be treated as disposable. "
                            "Return only JSON matching the schema. "
                            "Allowed importance: high, medium, low. "
                            "Allowed suggested_action: keep, archive, trash, review."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "sender_email": sender_email,
                                "sender_domain": sender_domain,
                                "subject": subject,
                                "snippet": snippet,
                                "labels": labels,
                                "has_unsubscribe": has_unsubscribe,
                            }
                        ),
                    },
                ],
            },
            timeout=30.0,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        try:
            return normalize_llm_classification(json.loads(content))
        except json.JSONDecodeError:
            return None


def normalize_llm_classification(payload: dict[str, Any] | None) -> dict | None:
    if not isinstance(payload, dict):
        return None

    category = str(payload.get("category", "unknown")).strip().lower()
    importance = str(payload.get("importance", "medium")).strip().lower()
    suggested_action = str(payload.get("suggested_action", "review")).strip().lower()
    reason = str(payload.get("reason", "")).strip()

    try:
        confidence = float(payload.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    if category not in ALLOWED_CATEGORIES:
        category = "unknown"
    if importance not in ALLOWED_IMPORTANCE:
        importance = "medium"
    if suggested_action not in ALLOWED_ACTIONS:
        suggested_action = "review"

    confidence = max(0.0, min(confidence, 1.0))
    if not reason:
        reason = "LLM classification returned without an explanation"

    return {
        "category": category,
        "importance": importance,
        "suggested_action": suggested_action,
        "confidence": confidence,
        "reason": reason,
    }
