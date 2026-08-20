"""
Authentication module — Emergent-managed Google Auth.

Flow (web):
  1. Frontend redirects user to https://auth.emergentagent.com/?redirect=<frontend_url>
  2. After Google login, user lands at <frontend_url>#session_id=<id>
  3. Frontend calls POST /api/auth/session with { session_id }
  4. Backend calls Emergent /session-data endpoint, upserts user, creates session,
     sets httpOnly cookie, returns user info.
  5. Subsequent requests carry the cookie; require_auth resolves the user.
"""
import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, Request, Response, HTTPException, Depends, Cookie, Header
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr

from db import db
from models import User, UserPublic, utcnow, new_id

logger = logging.getLogger("twt.auth")

router = APIRouter(prefix="/auth", tags=["auth"])

EMERGENT_SESSION_DATA_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"
EMERGENT_AUTH_LOGIN_URL = "https://auth.emergentagent.com/"

SESSION_COOKIE_NAME = os.environ.get("SESSION_COOKIE_NAME", "twt_session")
ENV = os.environ.get("ENV", "dev")
SESSION_TTL_DAYS = 7


# ─────────────────────────────────────────────────────────────
# Request/Response models
# ─────────────────────────────────────────────────────────────
class SessionExchangeRequest(BaseModel):
    session_id: str


class DevLoginRequest(BaseModel):
    email: EmailStr
    name: Optional[str] = None


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
async def _upsert_user(email: str, name: str, picture: Optional[str], google_id: Optional[str]) -> dict:
    """Upsert user by email — return the user dict (without _id)."""
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        updates = {}
        if name and existing.get("name") != name:
            updates["name"] = name
        if picture and existing.get("avatar_url") != picture:
            updates["avatar_url"] = picture
        if google_id and not existing.get("google_id"):
            updates["google_id"] = google_id
        if updates:
            await db.users.update_one({"user_id": existing["user_id"]}, {"$set": updates})
            existing.update(updates)
        logger.info("auth.user.existing user_id=%s email=%s", existing["user_id"], email)
        return existing

    user_id = new_id("user_")
    new_user = {
        "user_id": user_id,
        "google_id": google_id,
        "email": email,
        "name": name or email.split("@")[0],
        "avatar_url": picture,
        "home_currency_default": "EUR",
        "created_at": utcnow().isoformat(),
    }
    await db.users.insert_one(new_user)
    logger.info("auth.user.created user_id=%s email=%s", user_id, email)
    return {k: v for k, v in new_user.items() if k != "_id"}


async def _create_session(user_id: str, session_token: str) -> None:
    expires_at = utcnow() + timedelta(days=SESSION_TTL_DAYS)
    await db.user_sessions.insert_one({
        "session_token": session_token,
        "user_id": user_id,
        "expires_at": expires_at,
        "created_at": utcnow(),
    })


def _set_session_cookie(response: Response, session_token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        max_age=SESSION_TTL_DAYS * 24 * 3600,
        httponly=True,
        secure=True,        # required for SameSite=None; behind HTTPS ingress
        samesite="none",    # cross-site cookie for web callback flow
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/", samesite="none", secure=True)


async def _resolve_session_token(
    session_token_cookie: Optional[str],
    authorization: Optional[str],
) -> Optional[str]:
    if session_token_cookie:
        return session_token_cookie
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return None


async def require_auth(
    request: Request,
    session_token_cookie: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    authorization: Optional[str] = Header(default=None),
) -> dict:
    """Dependency: returns current user dict or raises 401."""
    token = await _resolve_session_token(session_token_cookie, authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    session_doc = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not session_doc:
        raise HTTPException(status_code=401, detail="Session not found")

    expires_at = session_doc["expires_at"]
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < utcnow():
        raise HTTPException(status_code=401, detail="Session expired")

    user_doc = await db.users.find_one({"user_id": session_doc["user_id"]}, {"_id": 0})
    if not user_doc:
        raise HTTPException(status_code=401, detail="User not found")
    return user_doc


# ─────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────
@router.get("/google/login")
async def google_login(redirect: Optional[str] = None):
    """
    Redirects to Emergent-managed Google Auth.
    The `redirect` query param is the frontend URL that will receive #session_id=.
    """
    if not redirect:
        raise HTTPException(status_code=400, detail="Missing redirect param")
    target = f"{EMERGENT_AUTH_LOGIN_URL}?redirect={redirect}"
    logger.info("auth.google.login redirect=%s", redirect)
    return RedirectResponse(target, status_code=302)


@router.post("/session")
async def exchange_session(
    body: SessionExchangeRequest,
    response: Response,
):
    """
    Exchange the temporary session_id (from Emergent redirect fragment) for a
    persistent session cookie. Called by the frontend right after OAuth redirect.
    """
    async with httpx.AsyncClient(timeout=10.0) as http_client:
        try:
            r = await http_client.get(
                EMERGENT_SESSION_DATA_URL,
                headers={"X-Session-ID": body.session_id},
            )
        except httpx.HTTPError as e:
            logger.exception("auth.session.emergent_error err=%s", e)
            raise HTTPException(status_code=502, detail="Auth provider unreachable")

    if r.status_code != 200:
        logger.warning("auth.session.rejected status=%s body=%s", r.status_code, r.text[:200])
        raise HTTPException(status_code=401, detail="Invalid session_id")

    data = r.json()
    email = data.get("email")
    name = data.get("name") or ""
    picture = data.get("picture")
    session_token = data.get("session_token")
    google_id = data.get("id")

    if not email or not session_token:
        raise HTTPException(status_code=502, detail="Invalid auth provider payload")

    user = await _upsert_user(email=email, name=name, picture=picture, google_id=google_id)
    await _create_session(user_id=user["user_id"], session_token=session_token)
    _set_session_cookie(response, session_token)

    logger.info("auth.session.created user_id=%s email=%s", user["user_id"], email)
    return {
        "user": UserPublic(**user).model_dump(),
    }


@router.get("/me")
async def me(current_user: dict = Depends(require_auth)):
    return UserPublic(**current_user).model_dump()


@router.post("/logout")
async def logout(
    response: Response,
    session_token_cookie: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    authorization: Optional[str] = Header(default=None),
):
    token = await _resolve_session_token(session_token_cookie, authorization)
    if token:
        result = await db.user_sessions.delete_one({"session_token": token})
        logger.info("auth.logout deleted=%s", result.deleted_count)
    _clear_session_cookie(response)
    return {"ok": True}


@router.post("/dev-login")
async def dev_login(body: DevLoginRequest, response: Response):
    """
    DEV-ONLY endpoint. Active only if ENV=dev. Creates/logs a fake user
    without going through Google. Used by the testing agent.
    """
    if ENV != "dev":
        raise HTTPException(status_code=404, detail="Not found")

    user = await _upsert_user(
        email=body.email,
        name=body.name or body.email.split("@")[0].replace(".", " ").title(),
        picture=None,
        google_id=None,
    )
    session_token = f"dev_{new_id()}"
    await _create_session(user_id=user["user_id"], session_token=session_token)
    _set_session_cookie(response, session_token)

    logger.info("auth.dev_login user_id=%s email=%s", user["user_id"], body.email)
    return {
        "user": UserPublic(**user).model_dump(),
        "session_token": session_token,  # useful for Bearer testing
    }
