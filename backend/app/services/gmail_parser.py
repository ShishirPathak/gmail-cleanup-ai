from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parseaddr
from typing import Any


@dataclass
class GmailMessageRecord:
    gmail_message_id: str
    gmail_thread_id: str | None
    sender_name: str | None
    sender_email: str | None
    sender_domain: str | None
    subject: str | None
    snippet: str | None
    body_text: str | None
    gmail_labels: str | None
    gmail_label_ids: str | None
    has_unsubscribe: bool
    is_read: bool
    received_at: datetime | None


def normalize_gmail_message(payload: dict[str, Any]) -> GmailMessageRecord:
    headers = {
        header["name"].lower(): header["value"]
        for header in payload.get("payload", {}).get("headers", [])
    }
    sender_name, sender_email = parseaddr(headers.get("from", ""))
    sender_domain = sender_email.split("@", 1)[1].lower() if "@" in sender_email else None

    body_text = extract_gmail_body(payload.get("payload", {}))
    label_ids = payload.get("labelIds", [])
    internal_date = payload.get("internalDate")

    return GmailMessageRecord(
        gmail_message_id=payload["id"],
        gmail_thread_id=payload.get("threadId"),
        sender_name=sender_name or None,
        sender_email=sender_email or None,
        sender_domain=sender_domain,
        subject=headers.get("subject"),
        snippet=payload.get("snippet"),
        body_text=body_text,
        gmail_labels=",".join(label_ids) if label_ids else None,
        gmail_label_ids=",".join(label_ids) if label_ids else None,
        has_unsubscribe="list-unsubscribe" in headers or "unsubscribe" in (body_text or "").lower(),
        is_read="UNREAD" not in label_ids,
        received_at=(
            datetime.fromtimestamp(int(internal_date) / 1000, tz=timezone.utc)
            if internal_date
            else None
        ),
    )


def extract_gmail_body(payload: dict[str, Any]) -> str | None:
    body = payload.get("body", {})
    data = body.get("data")
    if data:
        decoded = decode_gmail_body(data)
        if decoded:
            return decoded

    for part in payload.get("parts", []) or []:
        mime_type = part.get("mimeType", "")
        if mime_type in {"text/plain", "text/html"}:
            decoded = decode_gmail_body(part.get("body", {}).get("data"))
            if decoded:
                return decoded

        nested = extract_gmail_body(part)
        if nested:
            return nested
    return None


def decode_gmail_body(value: str | None) -> str | None:
    if not value:
        return None
    try:
        padded = value + "=" * (-len(value) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("utf-8"))
        return decoded.decode("utf-8", errors="ignore")
    except Exception:
        return None
