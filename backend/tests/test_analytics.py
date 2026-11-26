from __future__ import annotations

from fastapi.testclient import TestClient


def test_stats_endpoint_all_ranges_and_insights(client: TestClient) -> None:
    res_90 = client.get("/api/v1/stats?range=90d")
    assert res_90.status_code == 200
    stats = res_90.json()

    assert stats["range"] == "90d"
    summary = stats["summary"]
    assert summary["delivery_count"] == 8
    assert summary["total_spend_cents"] > 0
    assert summary["avg_spend_per_week_cents"] > 0
    assert summary["total_food_weight_kg"] > 5.0
    assert summary["healthy_spend_share_pct"] > 0
    assert summary["repeat_purchase_share_pct"] > 50.0
    assert summary["food_spend_cents"] > summary["non_food_spend_cents"]

    # Bucket shares sum close to 100%
    buckets = stats["buckets"]
    assert len(buckets) >= 4
    total_share = sum(b["share_pct"] for b in buckets)
    assert 98.0 <= total_share <= 102.0

    # Periods trend matches 8 weekly deliveries
    assert len(stats["periods"]) == 8
    assert all(p["spend_cents"] > 0 for p in stats["periods"])

    # Product ranking excludes one-off purchases (delivery_hits >= 2), sorted by spend descending
    products = stats["products"]
    assert len(products) >= 10
    assert all(p["delivery_hits"] >= 2 for p in products)
    assert products[0]["total_spend_cents"] >= products[-1]["total_spend_cents"]
    assert any(len(p["price_history"]) >= 2 for p in products)

    # Demo price movements show both rising and falling prices
    price_changes = stats["price_changes"]
    assert len(price_changes) >= 2
    assert any(pc["delta_cents"] > 0 for pc in price_changes)
    assert any(pc["delta_cents"] < 0 for pc in price_changes)

    # Protein per Euro leaders sorted descending
    pv = stats["protein_value_leaders"]
    assert len(pv) >= 3
    assert pv[0]["protein_g_per_euro"] >= pv[1]["protein_g_per_euro"]

    # Habits & Wrapped superlatives
    habits = stats["habits"]
    assert habits["avg_days_between_deliveries"] == 7.0
    assert habits["favorite_weekday"] is not None
    assert len(habits["weekday_distribution"]) == 7
    assert habits["heaviest_product_name"] is not None
    assert habits["most_bought_product_name"] is not None
    assert habits["largest_delivery_cents"] >= habits["smallest_delivery_cents"] > 0

    # Shorter range (30d) contains strictly fewer deliveries than 90d
    res_30 = client.get("/api/v1/stats?range=30d")
    assert res_30.status_code == 200
    assert res_30.json()["summary"]["delivery_count"] < summary["delivery_count"]

    # All-time range works cleanly
    res_all = client.get("/api/v1/stats?range=all")
    assert res_all.status_code == 200
    assert res_all.json()["summary"]["delivery_count"] == 8
