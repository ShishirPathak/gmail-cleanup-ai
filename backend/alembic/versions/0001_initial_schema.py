"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-03-16 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("google_subject", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_google_subject"), "users", ["google_subject"], unique=True)
    op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)

    op.create_table(
        "gmail_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("google_account_email", sa.String(), nullable=False),
        sa.Column("google_subject", sa.String(), nullable=True),
        sa.Column("access_token_encrypted", sa.Text(), nullable=True),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=True),
        sa.Column("token_expiry", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scopes", sa.Text(), nullable=True),
        sa.Column("last_history_id", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_gmail_accounts_google_subject"), "gmail_accounts", ["google_subject"], unique=False)
    op.create_index(op.f("ix_gmail_accounts_id"), "gmail_accounts", ["id"], unique=False)

    op.create_table(
        "emails",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("gmail_account_id", sa.Integer(), nullable=True),
        sa.Column("gmail_message_id", sa.String(), nullable=False),
        sa.Column("gmail_thread_id", sa.String(), nullable=True),
        sa.Column("sender_name", sa.String(), nullable=True),
        sa.Column("sender_email", sa.String(), nullable=True),
        sa.Column("sender_domain", sa.String(), nullable=True),
        sa.Column("subject", sa.String(), nullable=True),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("gmail_labels", sa.Text(), nullable=True),
        sa.Column("gmail_label_ids", sa.Text(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=True),
        sa.Column("has_unsubscribe", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["gmail_account_id"], ["gmail_accounts.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_emails_gmail_message_id"), "emails", ["gmail_message_id"], unique=True)
    op.create_index(op.f("ix_emails_gmail_thread_id"), "emails", ["gmail_thread_id"], unique=False)
    op.create_index(op.f("ix_emails_id"), "emails", ["id"], unique=False)
    op.create_index(op.f("ix_emails_sender_domain"), "emails", ["sender_domain"], unique=False)
    op.create_index(op.f("ix_emails_sender_email"), "emails", ["sender_email"], unique=False)

    op.create_table(
        "classifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("importance", sa.String(), nullable=True),
        sa.Column("suggested_action", sa.String(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["email_id"], ["emails.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_classifications_id"), "classifications", ["id"], unique=False)

    op.create_table(
        "user_actions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("email_id", sa.Integer(), nullable=False),
        sa.Column("action_taken", sa.String(), nullable=False),
        sa.Column("action_source", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["email_id"], ["emails.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_actions_id"), "user_actions", ["id"], unique=False)

    op.create_table(
        "email_embeddings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email_id", sa.Integer(), nullable=False),
        sa.Column("model_name", sa.String(), nullable=False),
        sa.Column("embedding", Vector(), nullable=False),
        sa.Column("embedded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["email_id"], ["emails.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email_id"),
    )
    op.create_index(op.f("ix_email_embeddings_id"), "email_embeddings", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_email_embeddings_id"), table_name="email_embeddings")
    op.drop_table("email_embeddings")
    op.drop_index(op.f("ix_user_actions_id"), table_name="user_actions")
    op.drop_table("user_actions")
    op.drop_index(op.f("ix_classifications_id"), table_name="classifications")
    op.drop_table("classifications")
    op.drop_index(op.f("ix_emails_sender_email"), table_name="emails")
    op.drop_index(op.f("ix_emails_sender_domain"), table_name="emails")
    op.drop_index(op.f("ix_emails_id"), table_name="emails")
    op.drop_index(op.f("ix_emails_gmail_thread_id"), table_name="emails")
    op.drop_index(op.f("ix_emails_gmail_message_id"), table_name="emails")
    op.drop_table("emails")
    op.drop_index(op.f("ix_gmail_accounts_id"), table_name="gmail_accounts")
    op.drop_index(op.f("ix_gmail_accounts_google_subject"), table_name="gmail_accounts")
    op.drop_table("gmail_accounts")
    op.drop_index(op.f("ix_users_id"), table_name="users")
    op.drop_index(op.f("ix_users_google_subject"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
