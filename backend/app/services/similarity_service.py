from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


def to_pgvector_literal(values) -> str:
    return "[" + ",".join(str(float(value)) for value in values) + "]"


class SimilarityService:
    def __init__(self, db: Session):
        self.db = db

    def find_similar_emails(
        self,
        *,
        user_id: int,
        email_id: int,
        embedding: list[float],
        limit: int = 5,
    ) -> list[dict]:
        sql = text(
            """
            SELECT
                e.id,
                e.sender_email,
                e.subject,
                e.snippet,
                lc.category,
                lc.suggested_action,
                ua.action_taken AS last_user_action,
                ee.embedding <-> CAST(:embedding AS vector) AS distance
            FROM email_embeddings ee
            JOIN emails e ON e.id = ee.email_id
            LEFT JOIN LATERAL (
                SELECT c.category, c.suggested_action
                FROM classifications c
                WHERE c.email_id = e.id
                ORDER BY c.created_at DESC
                LIMIT 1
            ) lc ON true
            LEFT JOIN LATERAL (
                SELECT action_taken
                FROM user_actions u
                WHERE u.email_id = e.id
                ORDER BY u.created_at DESC
                LIMIT 1
            ) ua ON true
            WHERE ee.email_id != :email_id
              AND e.user_id = :user_id
            ORDER BY ee.embedding <-> CAST(:embedding AS vector)
            LIMIT :limit
            """
        )
        rows = self.db.execute(
            sql,
            {
                "email_id": email_id,
                "user_id": user_id,
                "embedding": to_pgvector_literal(embedding),
                "limit": limit,
            },
        ).mappings()
        return [
            {
                "id": row["id"],
                "sender_email": row["sender_email"],
                "subject": row["subject"],
                "snippet": row["snippet"],
                "category": row["category"],
                "suggested_action": row["suggested_action"],
                "last_user_action": row["last_user_action"],
                "distance": float(row["distance"]),
            }
            for row in rows
        ]
