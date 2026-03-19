from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.gmail_account import GmailAccount
from app.services.account_service import AccountService
from app.services.gmail_parser import GmailMessageRecord, normalize_gmail_message


@dataclass
class GoogleIdentity:
    email: str
    name: str | None
    google_subject: str | None


@dataclass
class OAuthTokens:
    access_token: str | None
    refresh_token: str | None
    expiry: datetime | None
    scopes: list[str]


class GmailService:
    def __init__(self, db: Session | None = None):
        self.db = db
        self.account_service = AccountService(db) if db is not None else None

    def is_configured(self) -> bool:
        return bool(
            settings.google_client_id
            and settings.google_client_secret
            and settings.google_redirect_uri
        )

    def build_authorization_url(self, state: str) -> tuple[str, str | None]:
        from google_auth_oauthlib.flow import Flow

        flow = Flow.from_client_config(
            self._oauth_client_config(),
            scopes=settings.google_scopes,
            redirect_uri=settings.google_redirect_uri,
        )
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            state=state,
        )
        return auth_url, getattr(flow, "code_verifier", None)

    def exchange_code(self, code: str, code_verifier: str | None = None) -> OAuthTokens:
        from google_auth_oauthlib.flow import Flow

        flow = Flow.from_client_config(
            self._oauth_client_config(),
            scopes=settings.google_scopes,
            redirect_uri=settings.google_redirect_uri,
        )
        if code_verifier:
            flow.code_verifier = code_verifier
        flow.fetch_token(code=code)
        credentials = flow.credentials
        return OAuthTokens(
            access_token=credentials.token,
            refresh_token=credentials.refresh_token,
            expiry=credentials.expiry,
            scopes=list(credentials.scopes or settings.google_scopes),
        )

    def fetch_identity(self, tokens: OAuthTokens) -> GoogleIdentity:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        credentials = Credentials(
            token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            scopes=tokens.scopes,
        )
        oauth2 = build("oauth2", "v2", credentials=credentials, cache_discovery=False)
        profile = oauth2.userinfo().get().execute()
        return GoogleIdentity(
            email=profile["email"],
            name=profile.get("name"),
            google_subject=profile.get("id"),
        )

    def get_gmail_client(self, account: GmailAccount):
        from googleapiclient.discovery import build

        credentials = self._build_credentials(account)
        return build("gmail", "v1", credentials=credentials, cache_discovery=False)

    def sync_recent_emails(
        self,
        *,
        user_id: int,
        account: GmailAccount,
        max_results: int | None = None,
    ) -> list[GmailMessageRecord]:
        gmail = self.get_gmail_client(account)
        response = (
            gmail.users()
            .messages()
            .list(userId="me", maxResults=max_results or settings.sync_page_size)
            .execute()
        )

        synced: list[GmailMessageRecord] = []
        for item in response.get("messages", []):
            raw_message = (
                gmail.users()
                .messages()
                .get(userId="me", id=item["id"], format="full")
                .execute()
            )
            synced.append(normalize_gmail_message(raw_message))

        return synced

    def archive_message(self, account: GmailAccount, gmail_message_id: str) -> None:
        gmail = self.get_gmail_client(account)
        gmail.users().messages().modify(
            userId="me",
            id=gmail_message_id,
            body={"removeLabelIds": ["INBOX"]},
        ).execute()

    def trash_message(self, account: GmailAccount, gmail_message_id: str) -> None:
        gmail = self.get_gmail_client(account)
        gmail.users().messages().trash(userId="me", id=gmail_message_id).execute()

    def mark_as_read(self, account: GmailAccount, gmail_message_id: str) -> None:
        gmail = self.get_gmail_client(account)
        gmail.users().messages().modify(
            userId="me",
            id=gmail_message_id,
            body={"removeLabelIds": ["UNREAD"]},
        ).execute()

    def apply_labels(
        self,
        account: GmailAccount,
        gmail_message_id: str,
        label_names: list[str],
    ) -> list[str]:
        gmail = self.get_gmail_client(account)
        existing = gmail.users().labels().list(userId="me").execute().get("labels", [])
        label_map = {label["name"].lower(): label["id"] for label in existing}
        label_ids: list[str] = []

        for name in label_names:
            normalized = name.strip()
            if not normalized:
                continue
            label_id = label_map.get(normalized.lower())
            if not label_id:
                created = (
                    gmail.users()
                    .labels()
                    .create(
                        userId="me",
                        body={
                            "name": normalized,
                            "labelListVisibility": "labelShow",
                            "messageListVisibility": "show",
                        },
                    )
                    .execute()
                )
                label_id = created["id"]
                label_map[normalized.lower()] = label_id
            label_ids.append(label_id)

        if label_ids:
            gmail.users().messages().modify(
                userId="me",
                id=gmail_message_id,
                body={"addLabelIds": label_ids},
            ).execute()

        return label_ids

    def _oauth_client_config(self) -> dict[str, Any]:
        return {
            "web": {
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [settings.google_redirect_uri],
            }
        }

    def _build_credentials(self, account: GmailAccount):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        if self.account_service is None or self.db is None:
            raise ValueError("Database session is required for account-backed Gmail access")

        access_token = self.account_service.get_access_token(account)
        refresh_token = self.account_service.get_refresh_token(account)

        expiry = account.token_expiry
        if expiry and expiry.tzinfo is not None:
            expiry = expiry.astimezone(timezone.utc).replace(tzinfo=None)

        credentials = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            scopes=(account.scopes or settings.google_oauth_scopes).split(","),
            expiry=expiry,
        )

        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            self.account_service.upsert_gmail_account(
                user_id=account.user_id,
                google_account_email=account.google_account_email,
                google_subject=account.google_subject,
                access_token=credentials.token,
                refresh_token=credentials.refresh_token,
                token_expiry=credentials.expiry,
                scopes=list(credentials.scopes or settings.google_scopes),
            )
            self.db.commit()

        return credentials
