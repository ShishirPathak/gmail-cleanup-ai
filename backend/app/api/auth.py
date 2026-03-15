from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/google/login")
def google_login():
    return {
        "message": "Google OAuth login endpoint placeholder. Next step: redirect user to Google consent screen."
    }


@router.get("/google/callback")
def google_callback():
    return {
        "message": "Google OAuth callback placeholder. Next step: exchange auth code for tokens."
    }