from app.services.embedding_service import (
    EmbeddingService,
    FakeEmbeddingProvider,
    build_embedding_text,
)


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
