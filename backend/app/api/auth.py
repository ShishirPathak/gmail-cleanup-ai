import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from oauthlib.oauth2.rfc6749.errors import OAuth2Error
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.security import create_access_token
from app.db.redis import redis_client
from app.db.session import get_db
from app.models.user import User
from app.services.account_service import AccountService
from app.services.gmail_service import GmailService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/dev-login")
def dev_login(db: Session = Depends(get_db)):
    if settings.environment.lower() == "production":
        raise HTTPException(status_code=404, detail="Not found")

    email = "demo.user@example.com"
    account_service = AccountService(db)
    user = account_service.upsert_google_user(
        google_subject=None,
        email=email,
        name="Demo User",
    )
    db.commit()

    access_token = create_access_token(str(user.id))
    return {
        "token": access_token,
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
        },
    }


@router.get("/google/login")
def google_login():
    gmail_service = GmailService()
    if not gmail_service.is_configured():
        raise HTTPException(status_code=503, detail="Google OAuth is not configured")

    state = secrets.token_urlsafe(32)
    auth_url, code_verifier = gmail_service.build_authorization_url(state)
    redis_client.setex(
        f"oauth_state:{state}",
        600,
        code_verifier or "pending",
    )
    return {"auth_url": auth_url, "state": state}


@router.get("/google/callback")
def google_callback(
    code: str = Query(...),
    state: str = Query(...),
    scope: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    redis_key = f"oauth_state:{state}"
    code_verifier = redis_client.get(redis_key)
    if not code_verifier:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
    redis_client.delete(redis_key)

    gmail_service = GmailService(db)
    if not gmail_service.is_configured():
        raise HTTPException(status_code=503, detail="Google OAuth is not configured")

    try:
        tokens = gmail_service.exchange_code(code, code_verifier=code_verifier)
    except Warning as warning:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Google granted a different scope set than the app requested.",
                "granted_scope": scope,
                "required_scope": ",".join(settings.google_scopes),
                "reason": str(warning),
            },
        ) from warning
    except OAuth2Error as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Google OAuth token exchange failed.",
                "granted_scope": scope,
                "required_scope": ",".join(settings.google_scopes),
                "reason": str(exc),
            },
        ) from exc
    identity = gmail_service.fetch_identity(tokens)

    account_service = AccountService(db)
    user = account_service.upsert_google_user(
        google_subject=identity.google_subject,
        email=identity.email,
        name=identity.name,
    )
    account = account_service.upsert_gmail_account(
        user_id=user.id,
        google_account_email=identity.email,
        google_subject=identity.google_subject,
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_expiry=tokens.expiry,
        scopes=tokens.scopes,
    )
    db.commit()

    access_token = create_access_token(str(user.id))
    redirect_url = (
        f"{settings.frontend_url}/?"
        f"{urlencode({'token': access_token, 'email': identity.email, 'account_id': account.id})}"
    )
    return RedirectResponse(url=redirect_url, status_code=302)


@router.get("/me")
def get_me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    account = AccountService(db).get_primary_account(current_user.id)
    return {
        "user": {
            "id": current_user.id,
            "email": current_user.email,
            "name": current_user.name,
        },
        "gmail_account": (
            {
                "id": account.id,
                "email": account.google_account_email,
                "is_active": account.is_active,
                "scopes": (account.scopes or "").split(",") if account.scopes else [],
            }
            if account
            else None
        ),
    }
