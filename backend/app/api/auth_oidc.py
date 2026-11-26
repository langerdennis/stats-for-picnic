from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.oidc_service import (
    SESSION_COOKIE_NAME,
    SESSION_TTL_SECONDS,
    TX_COOKIE_NAME,
    TX_TTL_SECONDS,
    OIDCError,
    build_authorization_url,
    complete_oidc_callback,
    get_session_user_from_cookie,
    is_session_user_allowed,
    seal_cookie_payload,
)
from app.services.settings_store import get_effective_oidc_config

router = APIRouter(prefix="/api/auth/oidc", tags=["oidc"])


def _external_base_url(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}"


def _is_https(request: Request) -> bool:
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    return proto.lower() == "https"


@router.get("/status")
def oidc_status(request: Request, db: Session = Depends(get_db)) -> dict:
    cfg = get_effective_oidc_config(db)
    enabled = bool(cfg["enabled"])
    raw_user = get_session_user_from_cookie(request.cookies.get(SESSION_COOKIE_NAME)) if enabled else None
    allowed_emails: list[str] = list(cfg["allowed_emails"])  # type: ignore[arg-type]
    user = raw_user if is_session_user_allowed(raw_user, allowed_emails) else None
    return {
        "enabled": enabled,
        "authenticated": (not enabled) or (user is not None),
        "provider_name": cfg["provider_name"],
        "user_email": user.get("email") if user else None,
        "user_name": user.get("name") if user else None,
    }


@router.get("/login")
async def oidc_login(request: Request, db: Session = Depends(get_db)) -> RedirectResponse:
    cfg = get_effective_oidc_config(db)
    if not cfg["enabled"]:
        return RedirectResponse(url="/", status_code=302)

    redirect_uri = f"{_external_base_url(request)}/api/auth/oidc/callback"
    try:
        auth_url, tx_cookie = await build_authorization_url(db, redirect_uri)
    except OIDCError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    resp = RedirectResponse(url=auth_url, status_code=302)
    resp.set_cookie(
        key=TX_COOKIE_NAME,
        value=tx_cookie,
        max_age=TX_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=_is_https(request),
    )
    return resp


@router.get("/callback")
async def oidc_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    if error:
        return RedirectResponse(url=f"/?oidc_error={quote(error)}", status_code=302)
    if not code or not state:
        return RedirectResponse(url="/?oidc_error=missing_code", status_code=302)

    try:
        user = await complete_oidc_callback(
            db,
            code=code,
            state=state,
            tx_cookie=request.cookies.get(TX_COOKIE_NAME),
        )
    except OIDCError as exc:
        return RedirectResponse(url=f"/?oidc_error={quote(str(exc))}", status_code=302)

    resp = RedirectResponse(url="/", status_code=302)
    resp.delete_cookie(TX_COOKIE_NAME)
    resp.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=seal_cookie_payload(user),
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=_is_https(request),
    )
    return resp


@router.post("/logout")
def oidc_logout() -> JSONResponse:
    resp = JSONResponse(content={"status": "ok"})
    resp.delete_cookie(SESSION_COOKIE_NAME)
    return resp
