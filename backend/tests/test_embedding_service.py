from app.services.embedding_service import (
    EmbeddingService,
    FakeEmbeddingProvider,
    build_embedding_text,
)
from app.services.llm_service import normalize_llm_classification


def test_fake_embedding_is_deterministic():
    provider = FakeEmbeddingProvider(dimension=8)
    first = provider.embed("hello")
    second = provider.embed("hello")
    assert first == second
    assert len(first) == 8


def test_embedding_service_uses_injected_provider():
    provider = FakeEmbeddingProvider(dimension=4)
    result = EmbeddingService(provider=provider).embed_text("sample")
    assert result.model_name == "fake-hash-v1"
    assert len(result.vector) == 4


def test_build_embedding_text_includes_key_fields():
    text = build_embedding_text(
        sender_name="Promo Team",
        sender_email="offers@example.com",
        sender_domain="example.com",
        subject="Weekend sale",
        snippet="Limited time offer",
        labels="INBOX,PROMOTIONS",
        has_unsubscribe=True,
    )
    assert "sender_email:offers@example.com" in text
    assert "unsubscribe:True" in text


def test_normalize_llm_classification_clamps_invalid_values():
    result = normalize_llm_classification(
        {
            "category": "totally-new-category",
            "importance": "urgent",
            "suggested_action": "delete_forever",
            "confidence": 4.2,
            "reason": "",
        }
    )
    assert result == {
        "category": "unknown",
        "importance": "medium",
        "suggested_action": "review",
        "confidence": 1.0,
        "reason": "LLM classification returned without an explanation",
    }
