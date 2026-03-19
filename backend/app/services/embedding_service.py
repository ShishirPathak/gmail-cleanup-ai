from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import settings


EMBEDDING_DIMENSION = settings.embedding_dimension


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> list[float]:
        ...


@dataclass
class EmbeddingResult:
    model_name: str
    vector: list[float]


class FakeEmbeddingProvider:
    def __init__(self, dimension: int = EMBEDDING_DIMENSION):
        self.dimension = dimension
        self.model_name = "fake-hash-v1"

    def embed(self, text: str) -> list[float]:
        values: list[float] = []

        for i in range(self.dimension):
            digest = hashlib.sha256(f"{text}|{i}".encode("utf-8")).digest()
            integer_value = int.from_bytes(digest[:8], byteorder="big", signed=False)
            normalized = ((integer_value % 2000000) / 1000000.0) - 1.0
            values.append(normalized)

        return values


class OpenAIEmbeddingProvider:
    def __init__(self):
        self.model_name = settings.embedding_model

    def embed(self, text: str) -> list[float]:
        if not settings.embedding_api_key:
            raise ValueError("EMBEDDING_API_KEY is required for the OpenAI embedding provider")

        response = httpx.post(
            f"{settings.embedding_base_url.rstrip('/')}/embeddings",
            headers={
                "Authorization": f"Bearer {settings.embedding_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.embedding_model,
                "input": text,
            },
            timeout=30.0,
        )
        response.raise_for_status()
        payload = response.json()
        return payload["data"][0]["embedding"]


class EmbeddingService:
    def __init__(self, provider: EmbeddingProvider | None = None):
        self.provider = provider or get_embedding_provider()
        self.model_name = getattr(self.provider, "model_name", settings.embedding_model)

    def embed_text(self, text: str) -> EmbeddingResult:
        return EmbeddingResult(
            model_name=self.model_name,
            vector=self.provider.embed(text),
        )


def get_embedding_provider() -> EmbeddingProvider:
    provider_name = settings.embedding_provider.lower()
    if provider_name == "openai":
        return OpenAIEmbeddingProvider()
    if provider_name == "fake":
        return FakeEmbeddingProvider()
    raise ValueError(f"Unsupported embedding provider: {settings.embedding_provider}")


def build_embedding_text(
    sender_name: str | None,
    sender_email: str | None,
    sender_domain: str | None,
    subject: str | None,
    snippet: str | None,
    labels: str | None,
    has_unsubscribe: bool,
) -> str:
    return " | ".join(
        [
            f"sender_name:{sender_name or ''}",
            f"sender_email:{sender_email or ''}",
            f"sender_domain:{sender_domain or ''}",
            f"subject:{subject or ''}",
            f"snippet:{snippet or ''}",
            f"labels:{labels or ''}",
            f"unsubscribe:{has_unsubscribe}",
        ]
    )


def generate_fake_embedding(text: str, dim: int = EMBEDDING_DIMENSION) -> list[float]:
    return FakeEmbeddingProvider(dim).embed(text)
