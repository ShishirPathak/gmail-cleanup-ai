from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.security import decrypt_secret, encrypt_secret
from app.models.gmail_account import GmailAccount
from app.models.user import User


class AccountService:
    def __init__(self, db: Session):
        self.db = db

    def get_primary_account(self, user_id: int) -> GmailAccount | None:
        return (
            self.db.query(GmailAccount)
            .filter(GmailAccount.user_id == user_id, GmailAccount.is_active.is_(True))
            .order_by(GmailAccount.id.asc())
            .first()
        )

    def upsert_google_user(
        self,
        *,
        google_subject: str | None,
        email: str,
        name: str | None,
    ) -> User:
        user = None
        if google_subject:
            user = self.db.query(User).filter(User.google_subject == google_subject).first()
        if not user:
            user = self.db.query(User).filter(User.email == email).first()
        if not user:
            user = User(email=email, name=name, google_subject=google_subject)
            self.db.add(user)
            self.db.flush()
        else:
            user.email = email
            user.name = name
            if google_subject:
                user.google_subject = google_subject
        return user

    def upsert_gmail_account(
        self,
        *,
        user_id: int,
        google_account_email: str,
        google_subject: str | None,
        access_token: str | None,
        refresh_token: str | None,
        token_expiry: datetime | None,
        scopes: list[str],
    ) -> GmailAccount:
        account = (
            self.db.query(GmailAccount)
            .filter(
                GmailAccount.user_id == user_id,
                GmailAccount.google_account_email == google_account_email,
            )
            .first()
        )
        if not account:
            account = GmailAccount(
                user_id=user_id,
                google_account_email=google_account_email,
            )
            self.db.add(account)

        account.google_subject = google_subject
        account.access_token_encrypted = encrypt_secret(access_token)
        if refresh_token:
            account.refresh_token_encrypted = encrypt_secret(refresh_token)
        account.token_expiry = token_expiry
        account.scopes = ",".join(scopes)
        account.is_active = True
        self.db.flush()
        return account

    def get_access_token(self, account: GmailAccount) -> str | None:
        return decrypt_secret(account.access_token_encrypted)

    def get_refresh_token(self, account: GmailAccount) -> str | None:
        return decrypt_secret(account.refresh_token_encrypted)
