from app.services.recommendation_policy import (
    classify_email,
    evaluate_risk_flags,
    summarize_similar_actions,
)


def test_protected_email_is_kept():
    result = classify_email(
        sender_email="alerts@bank.com",
        sender_domain="bank.com",
        subject="Your OTP code",
        snippet="Use this verification code",
        labels="INBOX",
        has_unsubscribe=False,
    )
    assert result["category"] == "important"
    assert result["suggested_action"] == "keep"
    assert result["confidence"] >= 0.95


def test_promotional_email_is_archived():
    result = classify_email(
        sender_email="offers@example.com",
        sender_domain="example.com",
        subject="Weekend sale",
        snippet="Limited time discount available",
        labels="INBOX,PROMOTIONS",
        has_unsubscribe=True,
    )
    assert result["category"] == "promotion"
    assert result["suggested_action"] == "archive"


def test_risk_flags_capture_sender_domain_patterns():
    flags = evaluate_risk_flags(
        sender_email="alerts@delta.com",
        sender_domain="delta.com",
        subject="Check in for your flight",
        snippet="Travel itinerary attached",
    )
    assert any("travel" in flag or "delta.com" in flag for flag in flags)


def test_similar_action_summary_returns_majority_vote():
    action, count = summarize_similar_actions(
        [
            {"last_user_action": "archive"},
            {"last_user_action": "archive"},
            {"last_user_action": "keep"},
        ]
    )
    assert action == "archive"
    assert count == 2
