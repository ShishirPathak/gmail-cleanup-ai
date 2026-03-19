from __future__ import annotations

import json

import httpx

from app.core.config import settings


class LLMService:
    def is_enabled(self) -> bool:
        return settings.llm_provider.lower() == "openai" and bool(settings.llm_api_key)

    def classify_email(
        self,
        *,
        sender_email: str | None,
        subject: str | None,
        snippet: str | None,
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
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Classify Gmail messages conservatively for inbox cleanup. "
                            "Return strict JSON with category, importance, suggested_action, confidence, reason. "
                            "Use only keep, archive, trash, review as suggested_action."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "sender_email": sender_email,
                                "subject": subject,
                                "snippet": snippet,
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
            return json.loads(content)
        except json.JSONDecodeError:
            return None
