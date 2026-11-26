from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import and_, delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import MealieMealplan, MealieRecipe, SyncRun, utcnow
from app.services.llm_enrichment import LLMEnrichmentError, score_recipe_with_llm
from app.services.scoring import score_recipe_from_nutrition
from app.services.settings_store import (
    get_effective_llm_config,
    get_effective_mealie_config,
    is_demo_mode,
)

logger = logging.getLogger("stats_for_picnic.mealie")


class MealieServiceError(Exception):
    """Raised when Mealie API communication fails."""


def is_mealie_configured(db: Session) -> bool:
    if is_demo_mode(db):
        return True
    url, token = get_effective_mealie_config(db)
    return bool(url and token)


def _date_to_iso_week(d: date) -> str:
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _build_demo_recipe_svg(title: str, accent: str, subtitle: str) -> bytes:
    safe_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    safe_sub = subtitle.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="640" height="400" viewBox="0 0 640 400">
  <rect width="640" height="400" fill="#F4F2EC"/>
  <circle cx="515" cy="95" r="110" fill="{accent}" fill-opacity="0.16"/>
  <circle cx="130" cy="310" r="135" fill="{accent}" fill-opacity="0.10"/>
  <rect x="36" y="36" width="568" height="328" rx="20" fill="none" stroke="#E5E4DF" stroke-width="2"/>
  <circle cx="320" cy="168" r="68" fill="#FFFFFF" stroke="{accent}" stroke-width="3"/>
  <circle cx="320" cy="168" r="46" fill="{accent}" fill-opacity="0.18"/>
  <path d="M294 172 C306 144, 334 144, 346 172" fill="none" stroke="{accent}" stroke-width="4" stroke-linecap="round"/>
  <circle cx="308" cy="182" r="6" fill="{accent}"/>
  <circle cx="332" cy="182" r="6" fill="{accent}"/>
  <text x="320" y="284" text-anchor="middle" font-family="-apple-system, BlinkMacSystemFont, Inter, sans-serif" font-size="22" font-weight="600" fill="#18181B">{safe_title}</text>
  <text x="320" y="314" text-anchor="middle" font-family="-apple-system, BlinkMacSystemFont, Inter, sans-serif" font-size="14" fill="#71717A">{safe_sub}</text>
</svg>"""
    return svg.encode("utf-8")


DEMO_RECIPES: list[dict[str, Any]] = [
    {
        "mealie_id": "demo-rec-lachs-bowl",
        "slug": "lachs-bowl-mit-brokkoli",
        "name": "Lachs-Bowl mit Brokkoli",
        "health_score": 88,
        "score_summary": "Proteinreich & viel frisches Gemüse",
        "protein_level": "hoch",
        "veggie_level": "hoch",
        "nova_estimate": 1,
        "accent": "#2E7D5B",
        "ingredients": [
            "250 g Wildlachsfilet",
            "300 g Bio Brokkoli",
            "150 g Bio Quinoa",
            "1 Avocado",
            "100 g Babyspinat",
            "1 EL Olivenöl",
        ],
        "nutrition": {"calories": "580", "proteinContent": "42", "fiberContent": "11", "sugarContent": "4"},
    },
    {
        "mealie_id": "demo-rec-linsen-curry",
        "slug": "rotes-linsen-spinat-curry",
        "name": "Rotes Linsen-Spinat-Curry",
        "health_score": 91,
        "score_summary": "Pflanzliches Protein & ballaststoffstark",
        "protein_level": "hoch",
        "veggie_level": "hoch",
        "nova_estimate": 1,
        "accent": "#2E7D5B",
        "ingredients": [
            "250 g Rote Linsen",
            "150 g Bio Babyspinat",
            "400 g gehackte Tomaten",
            "200 g Kichererbsen",
            "1 Zwiebel, Ingwer, Kurkuma",
        ],
        "nutrition": {"calories": "490", "proteinContent": "29", "fiberContent": "14", "sugarContent": "7"},
    },
    {
        "mealie_id": "demo-rec-haehnchen-pfanne",
        "slug": "haehnchen-paprika-pfanne",
        "name": "Hähnchen-Paprika-Pfanne",
        "health_score": 85,
        "score_summary": "Hoher Proteinanteil, gut sättigend",
        "protein_level": "hoch",
        "veggie_level": "mittel",
        "nova_estimate": 1,
        "accent": "#3B82F6",
        "ingredients": [
            "400 g Bio Hähnchenbrustfilet",
            "3 Paprika bunt",
            "250 g Rispentomaten",
            "1 EL Olivenöl",
            "Kräuter der Provence",
        ],
        "nutrition": {"calories": "460", "proteinContent": "46", "fiberContent": "6", "sugarContent": "6"},
    },
    {
        "mealie_id": "demo-rec-skyr-overnight",
        "slug": "skyr-beeren-hafer-bowl",
        "name": "Skyr-Beeren-Hafer-Bowl",
        "health_score": 84,
        "score_summary": "Frisch, proteinreich & unverarbeitet",
        "protein_level": "hoch",
        "veggie_level": "mittel",
        "nova_estimate": 1,
        "accent": "#7C3AED",
        "ingredients": [
            "250 g Arla Skyr Natur",
            "60 g Bio Haferflocken",
            "150 g TK Waldbeeren",
            "1/2 Banane",
        ],
        "nutrition": {"calories": "410", "proteinContent": "33", "fiberContent": "9", "sugarContent": "11"},
    },
    {
        "mealie_id": "demo-rec-vollkorn-pasta",
        "slug": "vollkorn-penne-pesto-tomate",
        "name": "Vollkorn-Penne mit Pesto & Tomaten",
        "health_score": 72,
        "score_summary": "Ausgewogene schnelle Alltagsmahlzeit",
        "protein_level": "mittel",
        "veggie_level": "mittel",
        "nova_estimate": 2,
        "accent": "#D97706",
        "ingredients": [
            "250 g Vollkorn Penne",
            "90 g Pesto Genovese",
            "250 g Rispentomaten",
            "100 g Körniger Frischkäse",
        ],
        "nutrition": {"calories": "610", "proteinContent": "24", "fiberContent": "10", "sugarContent": "6"},
    },
]


def seed_demo_mealie_data(db: Session, reference_date: date | None = None) -> dict[str, int]:
    """Seed realistic German Mealie recipes and meal plans for current + previous week."""
    today = reference_date or datetime.now(UTC).date()
    cache_dir = get_settings().image_cache_dir

    for rec in DEMO_RECIPES:
        svg_path = cache_dir / f"{rec['mealie_id']}.svg"
        if not svg_path.exists():
            svg_path.write_bytes(
                _build_demo_recipe_svg(rec["name"], rec["accent"], rec["score_summary"])
            )

        existing = db.get(MealieRecipe, rec["mealie_id"])
        if existing is None:
            db.add(
                MealieRecipe(
                    mealie_id=rec["mealie_id"],
                    slug=rec["slug"],
                    name=rec["name"],
                    mealie_updated_at="2026-11-20T12:00:00Z",
                    image_cached_path=str(svg_path),
                    ingredients_json=json.dumps(rec["ingredients"], ensure_ascii=False),
                    nutrition_json=json.dumps(rec["nutrition"]),
                    health_score=rec["health_score"],
                    score_summary=rec["score_summary"],
                    protein_level=rec["protein_level"],
                    veggie_level=rec["veggie_level"],
                    nova_estimate=rec["nova_estimate"],
                    scored_source="mealie_nutrition",
                    scored_at=utcnow(),
                )
            )
    db.flush()

    # Seed meal plans for current week (including today!) and previous week
    monday = today - timedelta(days=today.weekday())
    plan_specs: list[tuple[date, str, str]] = [
        (today, "dinner", "demo-rec-lachs-bowl"),
        (monday + timedelta(days=(today.weekday() + 1) % 7), "dinner", "demo-rec-linsen-curry"),
        (monday + timedelta(days=(today.weekday() + 2) % 7), "dinner", "demo-rec-haehnchen-pfanne"),
        (monday + timedelta(days=(today.weekday() + 3) % 7), "breakfast", "demo-rec-skyr-overnight"),
        # Previous week
        (monday - timedelta(days=6), "dinner", "demo-rec-vollkorn-pasta"),
        (monday - timedelta(days=4), "dinner", "demo-rec-linsen-curry"),
        (monday - timedelta(days=2), "dinner", "demo-rec-haehnchen-pfanne"),
    ]

    existing_plans = list(db.scalars(select(MealieMealplan)))
    if not existing_plans:
        for plan_dt, entry_type, rec_id in plan_specs:
            rec = next(r for r in DEMO_RECIPES if r["mealie_id"] == rec_id)
            db.add(
                MealieMealplan(
                    plan_date=plan_dt,
                    iso_week=_date_to_iso_week(plan_dt),
                    entry_type=entry_type,
                    mealie_recipe_id=rec_id,
                    title=rec["name"],
                )
            )
    db.commit()
    return {"recipes": len(DEMO_RECIPES), "plans": len(plan_specs)}


def _extract_ingredients(recipe_data: dict[str, Any]) -> list[str]:
    raw_list = recipe_data.get("recipeIngredient") or []
    result: list[str] = []
    for item in raw_list:
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
        elif isinstance(item, dict):
            display = item.get("display") or item.get("originalText") or item.get("note")
            if isinstance(display, str) and display.strip():
                result.append(display.strip())
    return result


async def score_single_recipe(
    db: Session,
    recipe: MealieRecipe,
    *,
    force: bool = False,
    llm_client: httpx.AsyncClient | None = None,
) -> MealieRecipe:
    """Compute or refresh the cached health score for a Mealie recipe."""
    if not force and recipe.health_score is not None and recipe.scored_at is not None:
        return recipe

    ingredients = json.loads(recipe.ingredients_json or "[]")
    nutrition = json.loads(recipe.nutrition_json or "{}")

    # 1. Try Mealie native nutrition first
    deterministic = score_recipe_from_nutrition(nutrition, ingredients)
    if deterministic is not None:
        score, summary, protein_lvl, veggie_lvl, nova_est = deterministic
        recipe.health_score = score
        recipe.score_summary = summary
        recipe.protein_level = protein_lvl
        recipe.veggie_level = veggie_lvl
        recipe.nova_estimate = nova_est
        recipe.scored_source = "mealie_nutrition"
        recipe.scored_at = utcnow()
        db.commit()
        return recipe

    # 2. Fallback to DeepSeek Flash if configured
    base_url, api_key, model, use_responses = get_effective_llm_config(db)
    if api_key:
        try:
            llm_res = await score_recipe_with_llm(
                recipe.name,
                ingredients,
                base_url=base_url,
                api_key=api_key,
                model=model,
                use_responses_api=use_responses,
                client=llm_client,
            )
            recipe.health_score = llm_res.health_score
            recipe.score_summary = llm_res.score_summary
            recipe.protein_level = llm_res.protein_level
            recipe.veggie_level = llm_res.veggie_level
            recipe.nova_estimate = llm_res.nova_estimate
            recipe.scored_source = "llm"
            recipe.scored_at = utcnow()
            db.commit()
            return recipe
        except LLMEnrichmentError as exc:
            logger.warning("LLM recipe scoring failed for %s: %s", recipe.name, exc)

    # 3. Graceful heuristic fallback when neither Mealie nutrition nor LLM key is set
    ing_lower = " ".join(ingredients).lower()
    has_veggie = any(
        k in ing_lower for k in ("brokkoli", "spinat", "tomate", "paprika", "gemüse", "salat", "linse")
    )
    has_protein = any(
        k in ing_lower for k in ("lachs", "hähnchen", "tofu", "skyr", "ei", "fisch", "linse", "bohne")
    )
    score = 68 + (10 if has_veggie else 0) + (8 if has_protein else 0)
    recipe.health_score = min(90, score)
    recipe.score_summary = "Geschätzte Alltagsmahlzeit (ohne Nährwertangaben)"
    recipe.protein_level = "hoch" if has_protein else "mittel"
    recipe.veggie_level = "hoch" if has_veggie else "mittel"
    recipe.nova_estimate = 2
    recipe.scored_source = "heuristic"
    recipe.scored_at = utcnow()
    db.commit()
    return recipe


async def sync_mealie(
    db: Session,
    *,
    weeks_back: int = 8,
    weeks_forward: int = 1,
    client: httpx.AsyncClient | None = None,
    llm_client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Read-only sync of Mealie weekly meal plans and referenced recipes."""
    if is_demo_mode(db):
        seeded = seed_demo_mealie_data(db)
        return {"status": "ok", "mode": "demo", **seeded}

    mealie_url, mealie_token = get_effective_mealie_config(db)
    if not mealie_url or not mealie_token:
        return {"status": "not_configured", "recipes": 0, "plans": 0}

    run = SyncRun(source="mealie", started_at=utcnow(), status="running")
    db.add(run)
    db.commit()

    close_client = client is None
    http = client or httpx.AsyncClient(
        timeout=15.0,
        headers={"Authorization": f"Bearer {mealie_token}"},
    )
    try:
        today = datetime.now(UTC).date()
        start_dt = today - timedelta(weeks=weeks_back)
        end_dt = today + timedelta(weeks=weeks_forward)

        resp = await http.get(
            f"{mealie_url}/api/households/mealplans",
            params={
                "start_date": start_dt.isoformat(),
                "end_date": end_dt.isoformat(),
                "perPage": 200,
            },
            headers={"Authorization": f"Bearer {mealie_token}"},
        )
        resp.raise_for_status()
        payload = resp.json()
        entries = payload.get("items", []) if isinstance(payload, dict) else payload

        # Replace mealplans inside synced window to stay idempotent
        db.execute(
            delete(MealieMealplan).where(
                and_(
                    MealieMealplan.plan_date >= start_dt,
                    MealieMealplan.plan_date <= end_dt,
                )
            )
        )
        db.flush()

        recipes_touched = 0
        plans_synced = 0

        for entry in entries:
            if not isinstance(entry, dict):
                continue
            raw_date = entry.get("date")
            if not raw_date:
                continue
            try:
                plan_dt = date.fromisoformat(str(raw_date)[:10])
            except ValueError:
                continue

            entry_type = str(entry.get("entryType") or "dinner").lower()
            recipe_summary = entry.get("recipe")
            title = str(entry.get("title") or "").strip()
            mealie_recipe_id: str | None = None

            if isinstance(recipe_summary, dict) and recipe_summary.get("id"):
                mealie_recipe_id = str(recipe_summary["id"])
                slug = str(recipe_summary.get("slug") or mealie_recipe_id)
                rec_name = str(recipe_summary.get("name") or title or slug)
                title = rec_name
                updated_at_str = str(
                    recipe_summary.get("updatedAt") or recipe_summary.get("dateUpdated") or ""
                )

                existing_rec = db.get(MealieRecipe, mealie_recipe_id)
                needs_refresh = (
                    existing_rec is None
                    or (updated_at_str and existing_rec.mealie_updated_at != updated_at_str)
                    or existing_rec.health_score is None
                )

                if needs_refresh:
                    rec_detail = recipe_summary
                    try:
                        detail_resp = await http.get(
                            f"{mealie_url}/api/recipes/{slug}",
                            headers={"Authorization": f"Bearer {mealie_token}"},
                        )
                        if detail_resp.status_code == 200:
                            rec_detail = detail_resp.json()
                    except Exception as exc:
                        logger.debug("Mealie recipe detail fetch failed for %s: %s", slug, exc)

                    ingredients = _extract_ingredients(rec_detail)
                    nutrition = rec_detail.get("nutrition") or {}
                    if not isinstance(nutrition, dict):
                        nutrition = {}

                    if existing_rec is None:
                        existing_rec = MealieRecipe(
                            mealie_id=mealie_recipe_id,
                            slug=slug,
                            name=rec_name,
                            mealie_updated_at=updated_at_str or None,
                            ingredients_json=json.dumps(ingredients, ensure_ascii=False),
                            nutrition_json=json.dumps(nutrition),
                        )
                        db.add(existing_rec)
                    else:
                        existing_rec.slug = slug
                        existing_rec.name = rec_name
                        existing_rec.mealie_updated_at = updated_at_str or existing_rec.mealie_updated_at
                        existing_rec.ingredients_json = json.dumps(ingredients, ensure_ascii=False)
                        existing_rec.nutrition_json = json.dumps(nutrition)
                        existing_rec.health_score = None
                    db.flush()
                    await score_single_recipe(db, existing_rec, force=True, llm_client=llm_client)
                    recipes_touched += 1

            db.add(
                MealieMealplan(
                    plan_date=plan_dt,
                    iso_week=_date_to_iso_week(plan_dt),
                    entry_type=entry_type,
                    mealie_recipe_id=mealie_recipe_id,
                    title=title or "Geplante Mahlzeit",
                )
            )
            plans_synced += 1

        run.status = "ok"
        run.finished_at = utcnow()
        run.summary = f"{plans_synced} Mealie-Planeinträge synchronisiert ({recipes_touched} Rezepte aktualisiert)."
        db.commit()
        return {"status": "ok", "mode": "live", "recipes": recipes_touched, "plans": plans_synced}
    except Exception as exc:
        run.status = "error"
        run.error = str(exc)[:500]
        run.finished_at = utcnow()
        db.commit()
        raise MealieServiceError(f"Mealie-Sync fehlgeschlagen: {exc}") from exc
    finally:
        if close_client:
            await http.aclose()


async def get_or_fetch_recipe_image(
    db: Session,
    mealie_id: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> tuple[bytes, str] | None:
    """Return cached Mealie recipe thumbnail bytes + media type, fetching & caching on miss."""
    recipe = db.get(MealieRecipe, mealie_id)
    if recipe is None:
        return None

    # 1. Disk cache hit
    if recipe.image_cached_path:
        cached = Path(recipe.image_cached_path)
        if cached.is_file():
            media_type = "image/svg+xml" if cached.suffix == ".svg" else "image/webp"
            return cached.read_bytes(), media_type

    # 2. Demo mode fallback SVG
    if is_demo_mode(db):
        svg_bytes = _build_demo_recipe_svg(recipe.name, "#2E7D5B", recipe.score_summary or "Rezept")
        target = get_settings().image_cache_dir / f"{mealie_id}.svg"
        target.write_bytes(svg_bytes)
        recipe.image_cached_path = str(target)
        db.commit()
        return svg_bytes, "image/svg+xml"

    # 3. Live Mealie proxy + disk cache
    mealie_url, mealie_token = get_effective_mealie_config(db)
    if not mealie_url or not mealie_token:
        return None

    close_client = client is None
    http = client or httpx.AsyncClient(timeout=12.0)
    try:
        img_url = f"{mealie_url}/api/media/recipes/{mealie_id}/images/min-original.webp"
        resp = await http.get(img_url, headers={"Authorization": f"Bearer {mealie_token}"})
        if resp.status_code != 200 or not resp.content:
            return None
        target = get_settings().image_cache_dir / f"{mealie_id}.webp"
        target.write_bytes(resp.content)
        recipe.image_cached_path = str(target)
        db.commit()
        content_type = resp.headers.get("content-type", "image/webp").split(";")[0].strip()
        return resp.content, content_type
    except Exception as exc:
        logger.debug("Mealie image fetch failed for %s: %s", mealie_id, exc)
        return None
    finally:
        if close_client:
            await http.aclose()


async def test_mealie_connection(
    mealie_url: str,
    mealie_token: str,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Check read-only Mealie connectivity via /api/users/self."""
    clean_url = mealie_url.rstrip("/")
    if not clean_url or not mealie_token:
        raise MealieServiceError("Mealie URL und API-Token sind erforderlich.")
    close_client = client is None
    http = client or httpx.AsyncClient(timeout=10.0)
    try:
        resp = await http.get(
            f"{clean_url}/api/users/self",
            headers={"Authorization": f"Bearer {mealie_token}"},
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "status": "ok",
            "username": data.get("username") or data.get("email") or "Mealie User",
        }
    except Exception as exc:
        raise MealieServiceError(f"Mealie-Verbindung fehlgeschlagen: {exc}") from exc
    finally:
        if close_client:
            await http.aclose()
