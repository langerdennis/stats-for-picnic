from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app


def test_healthcheck(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["demo_mode"] is True
    assert payload["version"] == "0.2.0"


def test_demo_dashboard_deliveries_and_mealie(client: TestClient) -> None:
    dash_resp = client.get("/api/v1/dashboard")
    assert dash_resp.status_code == 200
    dash = dash_resp.json()
    assert dash["demo_mode"] is True
    assert dash["picnic_status"] == "demo"
    assert len(dash["trend_8_weeks"]) == 8
    assert dash["current_week_metrics"]["score"] > 0
    assert dash["live_cart_item_count"] > 0
    assert len(dash["weekly_mealie_entries"]) >= 1

    # Check proxied recipe image returns SVG in demo mode
    first_rec = dash["weekly_mealie_entries"][0]["recipe"]
    assert first_rec is not None
    img_resp = client.get(first_rec["image_url"])
    assert img_resp.status_code == 200
    assert "image/svg+xml" in img_resp.headers["content-type"]

    # Check deliveries list
    del_resp = client.get("/api/v1/deliveries")
    assert del_resp.status_code == 200
    deliveries = del_resp.json()
    assert len(deliveries) == 8
    assert deliveries[0]["score"] is not None


def test_cart_1click_readd_and_remove_updates_score(client: TestClient) -> None:
    before = client.get("/api/v1/cart").json()
    initial_count = before["item_count"]

    # Add healthy high-protein Skyr +2
    after_add = client.post("/api/v1/cart/add", json={"product_id": "p_skyr", "count": 2})
    assert after_add.status_code == 200
    cart_added = after_add.json()
    assert cart_added["item_count"] == initial_count + 2

    # Remove 2 Skyr again
    after_rem = client.post("/api/v1/cart/remove", json={"product_id": "p_skyr", "count": 2})
    assert after_rem.status_code == 200
    assert after_rem.json()["item_count"] == initial_count


def test_staples_filters_and_product_override(client: TestClient) -> None:
    hp = client.get("/api/v1/staples?filter=high_protein").json()
    assert len(hp) >= 3
    assert all(p["bucket"] == "protein" or (p["protein_g_per_100g"] or 0) >= 12 for p in hp)

    fresh = client.get("/api/v1/staples?filter=fresh").json()
    assert len(fresh) >= 3
    assert all(p["bucket"] == "produce" for p in fresh)

    # 1-tap ignore chips as family snack -> cart score should rise!
    cart_before = client.get("/api/v1/cart").json()["metrics"]["score"]
    patch = client.patch(
        "/api/v1/products/p_chips",
        json={"ignored": True, "ignored_reason": "family"},
    )
    assert patch.status_code == 200
    updated_prod = patch.json()
    assert updated_prod["ignored"] is True
    assert updated_prod["manual_override"] is True

    cart_after = client.get("/api/v1/cart").json()["metrics"]["score"]
    assert cart_after >= cart_before


def test_settings_mask_secrets(client: TestClient) -> None:
    r1 = client.put(
        "/api/v1/settings/llm",
        json={
            "llm_base_url": "https://api.deepseek.com",
            "llm_api_key": "sk-super-secret-deepseek-key-999",
            "llm_model": "deepseek-flash",
            "llm_use_responses_api": True,
        },
    )
    assert r1.status_code == 200

    settings_resp = client.get("/api/v1/settings").json()
    assert settings_resp["llm_configured"] is True
    assert "super-secret" not in settings_resp["llm_api_key_masked"]
    assert "••••" in settings_resp["llm_api_key_masked"]


def test_tesserae_summary_and_eink_widget(client: TestClient) -> None:
    summary_resp = client.get("/api/v1/summary")
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert summary["picnic_status"] == "demo"
    assert summary["current_week"]["score"] > 0
    assert summary["live_cart"]["item_count"] > 0
    assert len(summary["trend_8_weeks"]) == 8
    assert summary["mealie_today"]["name"] == "Lachs-Bowl mit Brokkoli"
    assert summary["mealie_today"]["health_score"] == 88

    for size in ("sm", "md", "lg"):
        widget = client.get(f"/widget/eink?size={size}&theme=mono")
        assert widget.status_code == 200
        assert "text/html" in widget.headers["content-type"]
        assert "X-Frame-Options" not in widget.headers
        assert "<svg" in widget.text
        assert "#EAE8E1" in widget.text


def test_tesserae_api_key_protection(
    temp_data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("API_KEY", "tesserae-secret-key")
    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as secured_client:
        assert secured_client.get("/api/v1/summary").status_code == 401
        assert secured_client.get("/widget/eink").status_code == 401

        ok_bearer = secured_client.get(
            "/api/v1/summary",
            headers={"Authorization": "Bearer tesserae-secret-key"},
        )
        assert ok_bearer.status_code == 200

        ok_header = secured_client.get(
            "/widget/eink?size=md",
            headers={"X-API-Key": "tesserae-secret-key"},
        )
        assert ok_header.status_code == 200


def test_mealie_graceful_degradation_when_unconfigured(
    temp_data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("MEALIE_URL", "")
    monkeypatch.setenv("MEALIE_API_TOKEN", "")
    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as plain_client:
        res = plain_client.get("/api/v1/mealie/week")
        assert res.status_code == 200
        assert res.json() == []
        dash = plain_client.get("/api/v1/dashboard").json()
        assert dash["mealie_configured"] is False
        assert dash["weekly_mealie_entries"] == []


def test_runtime_app_settings_and_demo_clear(client: TestClient) -> None:
    # 1) Set API key + sync interval + switch DEMO_MODE off via Settings API
    upd = client.put(
        "/api/v1/settings/app",
        json={
            "demo_mode": False,
            "sync_interval_minutes": 30,
            "api_key": "runtime-secret-key-42",
        },
    )
    assert upd.status_code == 200

    s = client.get("/api/v1/settings").json()
    assert s["demo_mode"] is False
    assert s["sync_interval_minutes"] == 30
    assert s["api_key_enabled"] is True
    assert "runtime-secret" not in s["api_key_masked"]
    assert "••••" in s["api_key_masked"]

    # Tesserae endpoint now enforces runtime API key
    assert client.get("/api/v1/summary").status_code == 401
    assert (
        client.get("/api/v1/summary", headers={"X-API-Key": "runtime-secret-key-42"}).status_code
        == 200
    )

    # Clear API key via Settings API
    cleared = client.put("/api/v1/settings/app", json={"clear_api_key": True})
    assert cleared.status_code == 200
    assert client.get("/api/v1/summary").status_code == 200

    # Clear demo data cleanly
    wipe = client.post("/api/v1/settings/demo/clear")
    assert wipe.status_code == 200
    assert wipe.json()["deliveries_removed"] == 8
    assert client.get("/api/v1/deliveries").json() == []


def test_product_image_quick_wins_and_enrich_endpoint(client: TestClient) -> None:
    dash = client.get("/api/v1/dashboard").json()
    assert dash["healthy_streak_weeks"] >= 2
    assert dash["current_week_metrics"]["tier"]["goals_total"] == 4

    cart = client.get("/api/v1/cart").json()
    assert len(cart["quick_wins"]) >= 1
    assert cart["quick_wins"][0]["score_delta"] > 0
    assert cart["items"][0]["image_url"] == f"/api/v1/products/{cart['items'][0]['picnic_id']}/image"

    img = client.get(cart["items"][0]["image_url"])
    assert img.status_code == 200
    assert "image/svg+xml" in img.headers["content-type"]

    enrich = client.post("/api/v1/products/enrich")
    assert enrich.status_code == 200
    assert enrich.json()["status"] == "ok"


def test_v02_search_remove_wins_targets_backup_and_eink_streak(client: TestClient) -> None:
    # Live/demo Picnic search endpoint
    search = client.get("/api/v1/picnic/search?q=skyr")
    assert search.status_code == 200
    hits = search.json()
    assert len(hits) >= 1
    assert hits[0]["picnic_id"] == "p_skyr"

    # Detractor remove quick-wins present in demo cart
    cart = client.get("/api/v1/cart").json()
    assert len(cart["remove_wins"]) >= 1
    assert cart["remove_wins"][0]["score_delta"] > 0

    # Configurable scoring targets persisted & returned
    upd = client.put(
        "/api/v1/settings/app",
        json={
            "scoring_targets": {
                "protein_per_1000_kcal": 40,
                "fresh_share_pct": 38,
                "nova_1_2_share_pct": 80,
                "snack_share_pct": 12,
            }
        },
    )
    assert upd.status_code == 200
    settings_out = client.get("/api/v1/settings").json()
    assert settings_out["scoring_targets"]["protein_per_1000_kcal"] == 40.0

    # 1-click SQLite online backup download
    backup = client.get("/api/v1/settings/backup")
    assert backup.status_code == 200
    assert backup.content.startswith(b"SQLite format 3\x00")
    assert "attachment" in backup.headers.get("content-disposition", "")

    # Tesserae summary + E-Ink SERIE badge & lg delivery slot
    summary = client.get("/api/v1/summary").json()
    assert summary["healthy_streak_weeks"] >= 2
    widget_lg = client.get("/widget/eink?size=lg&theme=mono")
    assert widget_lg.status_code == 200
    assert "SERIE" in widget_lg.text



