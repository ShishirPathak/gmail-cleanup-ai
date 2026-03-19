from __future__ import annotations

from collections import Counter


PROTECTED_KEYWORDS = {
    "otp": "security code / OTP",
    "verification": "account verification",
    "password reset": "account recovery",
    "invoice": "invoice or billing",
    "receipt": "receipt or proof of purchase",
    "interview": "job interview",
    "travel": "travel itinerary",
    "booking": "travel booking",
    "flight": "travel booking",
    "bank": "banking communication",
    "statement": "financial statement",
    "security alert": "security alert",
}

PROTECTED_SENDER_PATTERNS = [
    "noreply@accounts.google.com",
    "no-reply@accounts.google.com",
    "alerts@",
]

PROTECTED_DOMAIN_FRAGMENTS = [
    "bank",
    "chase",
    "wellsfargo",
    "americanexpress",
    "delta.com",
    "united.com",
    "airbnb.com",
    "expedia",
    "linkedin.com",
]

PROMO_WORDS = [
    "sale",
    "discount",
    "offer",
    "register now",
    "limited time",
    "deal",
    "webinar",
    "exclusive",
    "save big",
    "newsletter",
]


def evaluate_risk_flags(
    *,
    sender_email: str | None,
    sender_domain: str | None,
    subject: str | None,
    snippet: str | None,
) -> list[str]:
    text = f"{subject or ''} {snippet or ''}".lower()
    email = (sender_email or "").lower()
    domain = (sender_domain or "").lower()

    flags: list[str] = []

    for keyword, label in PROTECTED_KEYWORDS.items():
        if keyword in text:
            flags.append(label)

    for pattern in PROTECTED_SENDER_PATTERNS:
        if pattern in email:
            flags.append(f"protected sender pattern '{pattern}'")

    for fragment in PROTECTED_DOMAIN_FRAGMENTS:
        if fragment in domain:
            flags.append(f"protected sender domain '{fragment}'")

    return list(dict.fromkeys(flags))


def classify_email(
    *,
    sender_email: str | None = None,
    sender_domain: str | None = None,
    subject: str | None,
    snippet: str | None,
    labels: str | None,
    has_unsubscribe: bool,
) -> dict:
    text = f"{subject or ''} {snippet or ''}".lower()
    labels_text = (labels or "").lower()
    risk_flags = evaluate_risk_flags(
        sender_email=sender_email,
        sender_domain=sender_domain,
        subject=subject,
        snippet=snippet,
    )

    if risk_flags:
        return {
            "source": "rule",
            "category": "important",
            "importance": "high",
            "suggested_action": "keep",
            "confidence": 0.97,
            "reason": "protected because " + ", ".join(risk_flags),
            "risk_flags": risk_flags,
        }

    score = 0
    reasons = []

    if "promotions" in labels_text:
        score += 20
        reasons.append("gmail promotions label")

    for word in PROMO_WORDS:
        if word in text:
            score += 10
            reasons.append(f"contains '{word}'")
            break

    if has_unsubscribe:
        score += 15
        reasons.append("unsubscribe detected")

    if score >= 30:
        return {
            "source": "rule",
            "category": "promotion",
            "importance": "low",
            "suggested_action": "archive",
            "confidence": 0.78,
            "reason": ", ".join(reasons),
            "risk_flags": [],
        }

    if "updates" in labels_text and has_unsubscribe:
        return {
            "source": "rule",
            "category": "newsletter",
            "importance": "low",
            "suggested_action": "archive",
            "confidence": 0.62,
            "reason": "gmail updates label and unsubscribe detected",
            "risk_flags": [],
        }

    return {
        "source": "rule",
        "category": "unknown",
        "importance": "medium",
        "suggested_action": "review",
        "confidence": 0.40,
        "reason": ", ".join(reasons) if reasons else "insufficient signal",
        "risk_flags": [],
    }


def summarize_similar_actions(similar_rows: list[dict]) -> tuple[str | None, int]:
    actions = [
        row["last_user_action"]
        for row in similar_rows
        if row.get("last_user_action") in {"keep", "archive", "trash"}
    ]
    if not actions:
        return None, 0

    winner, count = Counter(actions).most_common(1)[0]
    return winner, count
