from __future__ import annotations

import base64
import hashlib
import json
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient

from app.services import oidc_service


def _fake_id_token(claims: dict[str, Any]) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"RS256","typ":"JWT"}').rstrip(b"=").decode("ascii")
    body = (
        base64.urlsafe_b64encode(json.dumps(claims).encode("utf-8")).rstrip(b"=").decode("ascii")
    )
    return f"{header}.{body}.fake_sig"


def test_cart_refresh_and_dashboard_top_quick_win(client: TestClient) -> None:
    dash = client.get("/api/v1/dashboard")
    assert dash.status_code == 200
    payload = dash.json()
    assert payload["top_cart_quick_win"] is not None
    assert payload["top_cart_quick_win"]["score_delta"] > 0

    refreshed = client.post("/api/v1/cart/refresh")
    assert refreshed.status_code == 200
    cart = refreshed.json()
    assert cart["item_count"] > 0
    assert cart["metrics"]["score"] > 0


def test_oidc_protection_pkce_flow_and_email_allowlist(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issuer = "https://id.example.test"
    discovery_doc = {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/authorize",
        "token_endpoint": f"{issuer}/api/oidc/token",
        "userinfo_endpoint": f"{issuer}/api/oidc/userinfo",
    }
    captured_token_requests: list[dict[str, str]] = []
    active_user_claims: dict[str, Any] = {
        "sub": "user-1",
        "email": "dennis@example.test",
        "name": "Dennis",
    }

    def mock_handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == f"{issuer}/.well-known/openid-configuration":
            return httpx.Response(200, json=discovery_doc)
        if str(request.url) == f"{issuer}/api/oidc/token":
            parsed = {k: v[0] for k, v in parse_qs(request.content.decode("utf-8")).items()}
            captured_token_requests.append(parsed)
            return httpx.Response(
                200,
                json={
                    "access_token": "mock-access-token",
                    "token_type": "Bearer",
                    "id_token": _fake_id_token(active_user_claims),
                },
            )
        if str(request.url) == f"{issuer}/api/oidc/userinfo":
            return httpx.Response(200, json=active_user_claims)
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    real_async_client = httpx.AsyncClient

    def patched_async_client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    oidc_service._discovery_cache.clear()
    monkeypatch.setattr(oidc_service.httpx, "AsyncClient", patched_async_client)

    # 1) Save & enable OIDC with an email allowlist
    save_resp = client.put(
        "/api/v1/settings/oidc",
        json={
            "enabled": True,
            "issuer_url": issuer,
            "client_id": "stats-for-picnic-client",
            "allowed_emails": "dennis@example.test, partner@example.test",
            "provider_name": "PocketID",
        },
    )
    assert save_resp.status_code == 200

    # 2) Unauthenticated requests to Web-UI API routes are now blocked (401)
    assert client.get("/api/v1/dashboard").status_code == 401
    assert client.get("/api/v1/cart").status_code == 401
    assert client.get("/api/v1/settings").status_code == 401

    # 3) Health, OIDC status, Tesserae summary, and E-Ink widget remain accessible
    assert client.get("/api/health").status_code == 200
    status_before = client.get("/api/auth/oidc/status").json()
    assert status_before["enabled"] is True
    assert status_before["authenticated"] is False
    assert status_before["provider_name"] == "PocketID"
    assert client.get("/api/v1/summary").status_code == 200
    assert client.get("/widget/eink?size=md").status_code == 200

    # 4) Start PKCE login flow
    login_resp = client.get("/api/auth/oidc/login", follow_redirects=False)
    assert login_resp.status_code == 302
    loc = urlparse(login_resp.headers["location"])
    assert f"{loc.scheme}://{loc.netloc}{loc.path}" == f"{issuer}/authorize"
    qs = parse_qs(loc.query)
    assert qs["client_id"] == ["stats-for-picnic-client"]
    assert qs["code_challenge_method"] == ["S256"]
    state = qs["state"][0]
    code_challenge = qs["code_challenge"][0]

    # 5) Callback with unauthorized email must be rejected by allowlist
    active_user_claims = {"sub": "intruder", "email": "other@example.test", "name": "Other"}
    denied = client.get(
        f"/api/auth/oidc/callback?code=bad-user-code&state={state}",
        follow_redirects=False,
    )
    assert denied.status_code == 302
    assert "oidc_error=" in denied.headers["location"]
    assert client.get("/api/v1/dashboard").status_code == 401

    # 6) Callback with allowed email succeeds & verifies PKCE S256 verifier
    active_user_claims = {
        "sub": "user-1",
        "email": "dennis@example.test",
        "name": "Dennis",
    }
    ok_cb = client.get(
        f"/api/auth/oidc/callback?code=valid-code&state={state}",
        follow_redirects=False,
    )
    assert ok_cb.status_code == 302
    assert ok_cb.headers["location"] == "/"

    # Verify the PKCE verifier sent to token endpoint matches the S256 challenge
    last_token_req = captured_token_requests[-1]
    verifier = last_token_req["code_verifier"]
    expected_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )
    assert expected_challenge == code_challenge

    # 7) Authenticated session cookie now grants access to protected endpoints & discovery test
    status_after = client.get("/api/auth/oidc/status").json()
    assert status_after["authenticated"] is True
    assert status_after["user_email"] == "dennis@example.test"
    assert status_after["user_name"] == "Dennis"

    assert client.get("/api/v1/dashboard").status_code == 200
    assert client.post("/api/v1/settings/oidc/test").status_code == 200

    # 8) Removing dennis@example.test from allowed_emails revokes the existing cookie immediately
    revoke_resp = client.put(
        "/api/v1/settings/oidc",
        json={
            "enabled": True,
            "issuer_url": issuer,
            "client_id": "stats-for-picnic-client",
            "allowed_emails": "partner@example.test",
            "provider_name": "PocketID",
        },
    )
    assert revoke_resp.status_code == 200
    assert client.get("/api/v1/dashboard").status_code == 401
    assert client.get("/api/auth/oidc/status").json()["authenticated"] is False

    # 9) Emergency env escape hatch OIDC_DISABLE=true restores access immediately
    from app.config import get_settings

    monkeypatch.setenv("OIDC_DISABLE", "true")
    get_settings.cache_clear()
    assert client.get("/api/v1/dashboard").status_code == 200
    assert client.get("/api/auth/oidc/status").json()["enabled"] is False
    monkeypatch.setenv("OIDC_DISABLE", "false")
    get_settings.cache_clear()

    # 10) Logout revokes cookie session
    logout = client.post("/api/auth/oidc/logout")
    assert logout.status_code == 200
    assert client.get("/api/v1/dashboard").status_code == 401


def test_smart_restock_product_macro_patch_re_enrich_and_ha_summary(client: TestClient) -> None:
    # Smart Restock suggests recurring staples missing from the current cart
    cart = client.get("/api/v1/cart").json()
    cart_ids = {item["picnic_id"] for item in cart["items"]}
    restock = cart["restock_suggestions"]
    assert len(restock) >= 1
    assert all(r["picnic_id"] not in cart_ids for r in restock)
    assert all(r["hits_in_recent_deliveries"] >= 2 for r in restock)

    # Adding a suggested restock item removes it from restock_suggestions
    first_restock_id = restock[0]["picnic_id"]
    after_add = client.post(
        "/api/v1/cart/add", json={"product_id": first_restock_id, "count": 1}
    ).json()
    assert all(r["picnic_id"] != first_restock_id for r in after_add["restock_suggestions"])

    # Patch parsed_weight_g and macros directly on a product
    patched = client.patch(
        "/api/v1/products/p_skyr",
        json={
            "parsed_weight_g": 450,
            "kcal_per_100g": 64,
            "protein_g_per_100g": 11.2,
            "sugar_g_per_100g": 3.8,
        },
    )
    assert patched.status_code == 200
    p_data = patched.json()
    assert p_data["parsed_weight_g"] == 450.0
    assert p_data["protein_g_per_100g"] == 11.2
    assert p_data["manual_override"] is True

    # Single-product re-enrich resets manual_override and runs enrichment
    re_enriched = client.post("/api/v1/products/p_spueltabs/re-enrich")
    assert re_enriched.status_code == 200
    re_data = re_enriched.json()
    assert re_data["enrichment_source"] == "rule"
    assert re_data["is_food"] is False

    # Home Assistant trigger fields in /api/v1/summary
    summary = client.get("/api/v1/summary").json()
    assert summary["picnic_reauth_required"] is False
    assert "next_delivery_slot" in summary
