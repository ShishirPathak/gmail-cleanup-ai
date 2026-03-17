import hashlib
from typing import List


EMBEDDING_DIMENSION = 16


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


def generate_fake_embedding(text: str, dim: int = EMBEDDING_DIMENSION) -> List[float]:
    """
    Deterministic placeholder embedding based on hashing.
    This is NOT semantically rich like a real embedding model,
    but it lets us wire and test the full vector pipeline end to end.
    """
    values: List[float] = []

    for i in range(dim):
        digest = hashlib.sha256(f"{text}|{i}".encode("utf-8")).digest()
        integer_value = int.from_bytes(digest[:8], byteorder="big", signed=False)

        # Map to roughly [-1, 1]
        normalized = ((integer_value % 2000000) / 1000000.0) - 1.0
        values.append(normalized)

    return values