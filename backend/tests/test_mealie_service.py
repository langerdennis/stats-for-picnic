from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from app.config import get_settings
from app.db import get_session_factory
from app.models import MealieMealplan, MealieRecipe
from app.services.mealie_service import get_or_fetch_recipe_image, sync_mealie
from app.services.settings_store import (
    KEY_LLM_API_KEY,
    KEY_LLM_BASE_URL,
    KEY_LLM_MODEL,
    KEY_MEALIE_API_TOKEN,
    KEY_MEALIE_URL,
    set_setting,
)


@pytest.mark.asyncio
async def test_mealie_live_sync_nutrition_llm_fallback_and_image_cache(
    temp_data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEMO_MODE", "false")
    get_settings.cache_clear()

    db = get_session_factory()()
    try:
        set_setting(db, KEY_MEALIE_URL, "https://mealie.local")
        set_setting(db, KEY_MEALIE_API_TOKEN, "mealie-secret-token")
        set_setting(db, KEY_LLM_BASE_URL, "https://api.deepseek.com")
        set_setting(db, KEY_LLM_API_KEY, "sk-test-llm")
        set_setting(db, KEY_LLM_MODEL, "deepseek-flash")

        today_str = date.today().isoformat()

        with respx.mock(assert_all_called=False) as mock:
            mock.get("https://mealie.local/api/households/mealplans").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "items": [
                            {
                                "date": today_str,
                                "entryType": "dinner",
                                "title": "Lachs Bowl",
                                "recipe": {
                                    "id": "rec-1",
                                    "slug": "lachs-bowl",
                                    "name": "Lachs Bowl",
                                    "updatedAt": "2026-11-25T10:00:00Z",
                                },
                            },
                            {
                                "date": today_str,
                                "entryType": "lunch",
                                "title": "Gemüse Curry",
                                "recipe": {
                                    "id": "rec-2",
                                    "slug": "gemuese-curry",
                                    "name": "Gemüse Curry",
                                    "updatedAt": "2026-11-25T11:00:00Z",
                                },
                            },
                        ]
                    },
                )
            )
            mock.get("https://mealie.local/api/recipes/lachs-bowl").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "id": "rec-1",
                        "slug": "lachs-bowl",
                        "name": "Lachs Bowl",
                        "recipeIngredient": [
                            {"display": "250 g Wildlachs"},
                            {"display": "300 g Brokkoli"},
                            {"display": "100 g Spinat"},
                        ],
                        "nutrition": {
                            "calories": "540",
                            "proteinContent": "42",
                            "fiberContent": "9",
                            "sugarContent": "4",
                        },
                    },
                )
            )
            mock.get("https://mealie.local/api/recipes/gemuese-curry").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "id": "rec-2",
                        "slug": "gemuese-curry",
                        "name": "Gemüse Curry",
                        "recipeIngredient": [
                            {"display": "200 g Kichererbsen"},
                            {"display": "2 Paprika"},
                        ],
                        "nutrition": {},
                    },
                )
            )
            mock.post("https://api.deepseek.com/v1/responses").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "output_text": json.dumps(
                            {
                                "health_score": 87,
                                "score_summary": "Gemüsereich & gut sättigend",
                                "protein_level": "mittel",
                                "veggie_level": "hoch",
                                "nova_estimate": 1,
                            }
                        )
                    },
                )
            )
            img_route = mock.get(
                "https://mealie.local/api/media/recipes/rec-1/images/min-original.webp"
            ).mock(
                return_value=httpx.Response(
                    200,
                    content=b"RIFF....WEBPfakeimage",
                    headers={"content-type": "image/webp"},
                )
            )

            res = await sync_mealie(db)
            assert res["status"] == "ok"
            assert res["plans"] == 2
            assert res["recipes"] == 2

            rec1 = db.get(MealieRecipe, "rec-1")
            assert rec1 is not None
            assert rec1.scored_source == "mealie_nutrition"
            assert rec1.health_score is not None and rec1.health_score >= 75

            rec2 = db.get(MealieRecipe, "rec-2")
            assert rec2 is not None
            assert rec2.scored_source == "llm"
            assert rec2.health_score == 87

            # Image proxy fetches once and serves from disk cache on second call
            first = await get_or_fetch_recipe_image(db, "rec-1")
            second = await get_or_fetch_recipe_image(db, "rec-1")
            assert first is not None and second is not None
            assert first[0] == b"RIFF....WEBPfakeimage"
            assert second[0] == b"RIFF....WEBPfakeimage"
            assert img_route.call_count == 1

            plans = db.query(MealieMealplan).all()
            assert len(plans) == 2
    finally:
        db.close()
