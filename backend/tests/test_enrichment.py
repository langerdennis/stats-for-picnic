from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from app.db import get_session_factory
from app.models import Product
from app.services.enrichment import enrich_pending_products
from app.services.settings_store import (
    KEY_LLM_API_KEY,
    KEY_LLM_BASE_URL,
    KEY_LLM_MODEL,
    KEY_LLM_USE_RESPONSES_API,
    set_setting,
)


@pytest.mark.asyncio
async def test_enrichment_non_food_openfoodfacts_llm_batch_and_manual_override(
    temp_data_dir: Path,
) -> None:
    db = get_session_factory()()
    try:
        set_setting(db, KEY_LLM_BASE_URL, "https://api.deepseek.com")
        set_setting(db, KEY_LLM_API_KEY, "sk-test-deepseek")
        set_setting(db, KEY_LLM_MODEL, "deepseek-flash")
        set_setting(db, KEY_LLM_USE_RESPONSES_API, "true")

        # 1) Non-food item (must be handled by rule without any HTTP call)
        db.add(
            Product(
                picnic_id="p_nonfood",
                name="Geschirrspültabs All-in-One",
                picnic_category="Haushalt",
                enrichment_source="pending",
            )
        )
        # 2) OpenFoodFacts GTIN hit
        db.add(
            Product(
                picnic_id="p_off",
                name="Arla Skyr Natur",
                unit_quantity="500 g",
                gtin="5711953027000",
                enrichment_source="pending",
            )
        )
        # 3) Product missing in OpenFoodFacts -> DeepSeek Flash Responses API batch
        db.add(
            Product(
                picnic_id="p_llm",
                name="Hausgemachter Hummus Pikant",
                unit_quantity="200 g",
                enrichment_source="pending",
            )
        )
        # 4) Manual override product (must NEVER be overwritten)
        db.add(
            Product(
                picnic_id="p_manual",
                name="Spezial Riegel",
                bucket="protein",
                nova_group=2,
                ignored=True,
                ignored_reason="family",
                manual_override=True,
                enrichment_source="pending",
            )
        )
        db.commit()

        captured_llm_payload: dict = {}

        with respx.mock(assert_all_called=False) as mock:
            mock.get("https://de.openfoodfacts.org/api/v2/product/5711953027000.json").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "status": 1,
                        "product": {
                            "code": "5711953027000",
                            "product_name_de": "Arla Skyr Natur",
                            "categories_tags": ["en:dairies", "en:skyr"],
                            "nova_group": 1,
                            "nutriscore_grade": "a",
                            "nutriments": {
                                "energy-kcal_100g": 63,
                                "proteins_100g": 11.0,
                                "carbohydrates_100g": 4.0,
                                "sugars_100g": 4.0,
                                "fat_100g": 0.2,
                                "fiber_100g": 0.0,
                            },
                        },
                    },
                )
            )
            mock.get("https://de.openfoodfacts.org/cgi/search.pl").mock(
                return_value=httpx.Response(200, json={"products": []})
            )

            def llm_handler(request: httpx.Request) -> httpx.Response:
                nonlocal captured_llm_payload
                captured_llm_payload = json.loads(request.content.decode("utf-8"))
                return httpx.Response(
                    200,
                    json={
                        "output_text": json.dumps(
                            {
                                "products": [
                                    {
                                        "picnic_id": "p_llm",
                                        "is_food": True,
                                        "bucket": "whole_food",
                                        "kcal_per_100g": 240.0,
                                        "protein_g_per_100g": 8.0,
                                        "carbs_g_per_100g": 15.0,
                                        "sugar_g_per_100g": 1.2,
                                        "fat_g_per_100g": 16.0,
                                        "fiber_g_per_100g": 5.5,
                                        "nova_group": 2,
                                        "confidence": 0.85,
                                    }
                                ]
                            }
                        )
                    },
                )

            mock.post("https://api.deepseek.com/v1/responses").mock(side_effect=llm_handler)

            stats = await enrich_pending_products(db)

        assert stats["rule_non_food"] == 1
        assert stats["openfoodfacts"] == 1
        assert stats["llm"] == 1
        assert stats["skipped_manual"] == 1

        # Verify DeepSeek Flash disabled thinking mode and strict json_schema
        assert captured_llm_payload["model"] == "deepseek-flash"
        assert captured_llm_payload["thinking"] == {"type": "disabled"}
        assert captured_llm_payload["text"]["format"]["type"] == "json_schema"

        nonfood = db.get(Product, "p_nonfood")
        assert nonfood is not None
        assert nonfood.is_food is False
        assert nonfood.bucket == "household"
        assert nonfood.ignored is True
        assert nonfood.enrichment_source == "rule"

        off_prod = db.get(Product, "p_off")
        assert off_prod is not None
        assert off_prod.enrichment_source == "openfoodfacts"
        assert off_prod.bucket == "protein"
        assert off_prod.protein_g_per_100g == 11.0
        assert off_prod.nova_group == 1

        llm_prod = db.get(Product, "p_llm")
        assert llm_prod is not None
        assert llm_prod.enrichment_source == "llm"
        assert llm_prod.bucket == "whole_food"
        assert llm_prod.kcal_per_100g == 240.0

        manual_prod = db.get(Product, "p_manual")
        assert manual_prod is not None
        assert manual_prod.bucket == "protein"
        assert manual_prod.ignored is True
        assert manual_prod.ignored_reason == "family"
    finally:
        db.close()


@pytest.mark.asyncio
async def test_enrichment_chat_completions_blank_json_retry(temp_data_dir: Path) -> None:
    """Verify DeepSeek json_object whitespace-only response triggers 1x automatic retry."""
    db = get_session_factory()()
    try:
        set_setting(db, KEY_LLM_BASE_URL, "https://api.deepseek.com")
        set_setting(db, KEY_LLM_API_KEY, "sk-test-deepseek")
        set_setting(db, KEY_LLM_MODEL, "deepseek-flash")
        set_setting(db, KEY_LLM_USE_RESPONSES_API, "false")

        db.add(
            Product(
                picnic_id="p_retry",
                name="Bio Linsen-Chips Meersalz",
                unit_quantity="100 g",
                enrichment_source="pending",
            )
        )
        db.commit()

        call_count = 0

        with respx.mock(assert_all_called=False) as mock:
            mock.get("https://de.openfoodfacts.org/cgi/search.pl").mock(
                return_value=httpx.Response(200, json={"products": []})
            )

            def chat_handler(request: httpx.Request) -> httpx.Response:
                nonlocal call_count
                call_count += 1
                body = json.loads(request.content.decode("utf-8"))
                assert body["response_format"] == {"type": "json_object"}
                assert body["thinking"] == {"type": "disabled"}
                if call_count == 1:
                    # Simulate DeepSeek replacing unparseable output with spaces
                    return httpx.Response(
                        200,
                        json={"choices": [{"message": {"content": "     \n  "}}]},
                    )
                return httpx.Response(
                    200,
                    json={
                        "choices": [
                            {
                                "message": {
                                    "content": json.dumps(
                                        {
                                            "products": [
                                                {
                                                    "picnic_id": "p_retry",
                                                    "is_food": True,
                                                    "bucket": "treat_snack",
                                                    "kcal_per_100g": 450.0,
                                                    "protein_g_per_100g": 13.0,
                                                    "carbs_g_per_100g": 56.0,
                                                    "sugar_g_per_100g": 3.0,
                                                    "fat_g_per_100g": 18.0,
                                                    "fiber_g_per_100g": 6.0,
                                                    "nova_group": 4,
                                                    "confidence": 0.82,
                                                }
                                            ]
                                        }
                                    )
                                }
                            }
                        ]
                    },
                )

            mock.post("https://api.deepseek.com/v1/chat/completions").mock(side_effect=chat_handler)

            stats = await enrich_pending_products(db)

        assert call_count == 2
        assert stats["llm"] == 1
        prod = db.get(Product, "p_retry")
        assert prod is not None
        assert prod.bucket == "treat_snack"
        assert prod.nova_group == 4
        assert prod.enrichment_source == "llm"
    finally:
        db.close()
