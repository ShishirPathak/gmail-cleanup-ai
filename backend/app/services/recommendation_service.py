from typing import Dict


def classify_email(subject: str, snippet: str, labels: str, has_unsubscribe: bool) -> Dict:
    text = f"{subject or ''} {snippet or ''}".lower()
    labels_text = (labels or "").lower()

    score = 0
    reasons = []

    protected_words = ["invoice", "receipt", "otp", "verification", "interview", "travel", "booking"]
    for word in protected_words:
        if word in text:
            return {
                "source": "rule",
                "category": "important",
                "importance": "high",
                "suggested_action": "keep",
                "confidence": 0.95,
                "reason": f"contains protected keyword '{word}'",
            }

    if "promotions" in labels_text:
        score += 20
        reasons.append("gmail promotions label")

    promo_words = [
        "sale",
        "discount",
        "offer",
        "register now",
        "limited time",
        "deal",
        "webinar",
        "exclusive",
        "save big",
    ]

    for word in promo_words:
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
            "confidence": 0.75,
            "reason": ", ".join(reasons),
        }

    return {
        "source": "rule",
        "category": "unknown",
        "importance": "medium",
        "suggested_action": "review",
        "confidence": 0.40,
        "reason": ", ".join(reasons) if reasons else "insufficient signal",
    }