from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.services.settings_store import get_effective_oidc_config

logger = logging.getLogger("stats_for_picnic.oidc")

SESSION_COOKIE_NAME = "sfp_session"
TX_COOKIE_NAME = "sfp_oidc_tx"
SESSION_TTL_SECONDS = 30 * 24 * 3600  # 30 days
TX_TTL_SECONDS = 10 * 60  # 10 minutes

_discovery_cache: dict[str, tuple[float, dict[str, Any]]] = {}


class OIDCError(Exception):
    """Raised when OIDC discovery, token exchange, or user validation fails."""


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def generate_pkce_pair() -> tuple[str, str]:
    verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def seal_cookie_payload(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return get_settings().get_fernet().encrypt(raw).decode("ascii")


def unseal_cookie_payload(token: str | None, max_age: int) -> dict[str, Any] | None:
    if not token:
        return None
    try:
        raw = get_settings().get_fernet().decrypt(token.encode("ascii"), ttl=max_age)
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def decode_jwt_payload_unverified(id_token: str) -> dict[str, Any]:
    """Extract claims from an ID token received directly over TLS from the token endpoint."""
    parts = id_token.split(".")
    if len(parts) < 2:
        return {}
    padded = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
        parsed = json.loads(decoded.decode("utf-8"))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


async def discover_oidc_provider(
    issuer_url: str,
    *,
    force_refresh: bool = False,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    clean = issuer_url.strip().rstrip("/")
    if not clean:
        raise OIDCError("OIDC Issuer URL fehlt.")

    cached = _discovery_cache.get(clean)
    now = time.monotonic()
    if cached and not force_refresh and (now - cached[0]) < 3600:
        return cached[1]

    url = f"{clean}/.well-known/openid-configuration"
    close_client = client is None
    http = client or httpx.AsyncClient(timeout=10.0)
    try:
        resp = await http.get(url)
        resp.raise_for_status()
        doc = resp.json()
        if not isinstance(doc, dict) or not doc.get("authorization_endpoint") or not doc.get("token_endpoint"):
            raise OIDCError("OIDC Discovery-Dokument enthält keine gültigen Endpoints.")
        _discovery_cache[clean] = (now, doc)
        return doc
    except OIDCError:
        raise
    except Exception as exc:
        raise OIDCError(f"OIDC Discovery fehlgeschlagen ({url}): {exc}") from exc
    finally:
        if close_client:
            await http.aclose()


async def build_authorization_url(
    db: Session,
    redirect_uri: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> tuple[str, str]:
    """Return (authorize_url, sealed_tx_cookie_value) using OIDC Authorization Code + PKCE S256."""
    cfg = get_effective_oidc_config(db)
    issuer = str(cfg["issuer_url"])
    client_id = str(cfg["client_id"])
    if not issuer or not client_id:
        raise OIDCError("OIDC ist nicht vollständig konfiguriert.")

    doc = await discover_oidc_provider(issuer, client=client)
    state = _b64url(secrets.token_bytes(24))
    verifier, challenge = generate_pkce_pair()

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": "openid profile email",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    auth_url = f"{doc['authorization_endpoint']}?{urlencode(params)}"
    tx_cookie = seal_cookie_payload(
        {
            "state": state,
            "verifier": verifier,
            "redirect_uri": redirect_uri,
        }
    )
    return auth_url, tx_cookie


async def complete_oidc_callback(
    db: Session,
    *,
    code: str,
    state: str,
    tx_cookie: str | None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Validate state, exchange code+PKCE verifier, enforce optional email allowlist, return session user."""
    tx = unseal_cookie_payload(tx_cookie, max_age=TX_TTL_SECONDS)
    if tx is None or not secrets.compare_digest(str(tx.get("state", "")), state):
        raise OIDCError("Ungültiger oder abgelaufener OIDC-State. Bitte Anmeldung neu starten.")

    cfg = get_effective_oidc_config(db)
    issuer = str(cfg["issuer_url"])
    client_id = str(cfg["client_id"])
    client_secret = str(cfg["client_secret"])
    allowed_emails: list[str] = list(cfg["allowed_emails"])  # type: ignore[arg-type]

    doc = await discover_oidc_provider(issuer, client=client)
    token_data: dict[str, str] = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": str(tx["redirect_uri"]),
        "client_id": client_id,
        "code_verifier": str(tx["verifier"]),
    }
    if client_secret:
        token_data["client_secret"] = client_secret

    close_client = client is None
    http = client or httpx.AsyncClient(timeout=12.0)
    try:
        token_resp = await http.post(
            str(doc["token_endpoint"]),
            data=token_data,
            headers={"Accept": "application/json"},
        )
        if token_resp.status_code >= 400:
            raise OIDCError(f"Token-Austausch fehlgeschlagen (HTTP {token_resp.status_code}).")
        tokens = token_resp.json()

        claims: dict[str, Any] = {}
        if isinstance(tokens.get("id_token"), str):
            claims.update(decode_jwt_payload_unverified(tokens["id_token"]))

        access_token = tokens.get("access_token")
        userinfo_ep = doc.get("userinfo_endpoint")
        if isinstance(access_token, str) and isinstance(userinfo_ep, str) and userinfo_ep:
            try:
                ui_resp = await http.get(
                    userinfo_ep,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                if ui_resp.status_code == 200 and isinstance(ui_resp.json(), dict):
                    claims.update(ui_resp.json())
            except Exception as exc:
                logger.debug("OIDC userinfo fetch skipped: %s", exc)

        email = str(claims.get("email") or "").strip().lower()
        name = str(
            claims.get("name")
            or claims.get("preferred_username")
            or email
            or claims.get("sub")
            or "Haushaltsmitglied"
        )
        sub = str(claims.get("sub") or email or name)

        if allowed_emails and (not email or email not in allowed_emails):
            raise OIDCError(
                f"Zugriff verweigert: '{email or 'unbekannt'}' ist nicht in der erlaubten E-Mail-Liste."
            )

        return {"sub": sub, "email": email, "name": name}
    finally:
        if close_client:
            await http.aclose()


def get_session_user_from_cookie(cookie_val: str | None) -> dict[str, Any] | None:
    return unseal_cookie_payload(cookie_val, max_age=SESSION_TTL_SECONDS)


def is_session_user_allowed(
    user: dict[str, Any] | None,
    allowed_emails: list[str],
) -> bool:
    if user is None:
        return False
    if not allowed_emails:
        return True
    email = str(user.get("email") or "").strip().lower()
    return bool(email and email in allowed_emails)
