"""Google OAuth login for the management UI and the session-based auth gate."""

from __future__ import annotations

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from .config import Settings

GOOGLE_METADATA_URL = "https://accounts.google.com/.well-known/openid-configuration"

router = APIRouter()


def build_oauth(settings: Settings) -> OAuth:
    """Construct the Authlib OAuth registry with a Google provider."""
    oauth = OAuth()
    oauth.register(
        name="google",
        server_metadata_url=GOOGLE_METADATA_URL,
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        client_kwargs={"scope": "openid email profile"},
    )
    return oauth


def resolve_login(email: str | None, settings: Settings) -> dict | None:
    """Return a user dict if `email` is on the allowlist, else None."""
    if not email:
        return None
    if email.lower() in settings.allowed_emails:
        return {"email": email.lower()}
    return None


def require_user(request: Request) -> dict:
    """UI auth gate: require a logged-in, allowlisted user or redirect to login."""
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/auth/login"})
    return user


@router.get("/auth/login")
async def login(request: Request):
    oauth: OAuth = request.app.state.oauth
    return await oauth.google.authorize_redirect(
        request, request.app.state.settings.oauth_redirect_uri
    )


@router.get("/auth/callback")
async def callback(request: Request):
    oauth: OAuth = request.app.state.oauth
    settings: Settings = request.app.state.settings
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as exc:  # noqa: BLE001 - surface auth failures as 401
        raise HTTPException(status_code=401, detail=f"login failed: {exc}") from exc

    userinfo = token.get("userinfo") or {}
    user = resolve_login(userinfo.get("email"), settings)
    if user is None:
        raise HTTPException(status_code=403, detail="this Google account is not authorized")
    request.session["user"] = user
    return RedirectResponse(url="/", status_code=303)


@router.get("/auth/logout")
async def logout(request: Request):
    request.session.pop("user", None)
    return RedirectResponse(url="/login", status_code=303)
