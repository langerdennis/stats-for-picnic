from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import MealieMealplan, MealieRecipe
from app.schemas import MealiePlanEntryOut, MealieRecipeOut
from app.services.mealie_service import (
    get_or_fetch_recipe_image,
    is_mealie_configured,
    score_single_recipe,
)
from app.services.scoring import iso_week_str

router = APIRouter(prefix="/api/v1/mealie", tags=["mealie"])


def _recipe_to_out(recipe: MealieRecipe) -> MealieRecipeOut:
    return MealieRecipeOut(
        mealie_id=recipe.mealie_id,
        slug=recipe.slug,
        name=recipe.name,
        image_url=f"/api/v1/mealie/recipes/{recipe.mealie_id}/image",
        health_score=recipe.health_score,
        score_summary=recipe.score_summary,
        protein_level=recipe.protein_level,
        veggie_level=recipe.veggie_level,
        nova_estimate=recipe.nova_estimate,
        scored_source=recipe.scored_source,
        ingredients=json.loads(recipe.ingredients_json or "[]"),
    )


@router.get("/week", response_model=list[MealiePlanEntryOut])
def get_mealie_week(
    iso_week: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[MealiePlanEntryOut]:
    if not is_mealie_configured(db):
        return []
    target_week = iso_week or iso_week_str(datetime.now(UTC))
    plans = list(
        db.scalars(
            select(MealieMealplan)
            .where(MealieMealplan.iso_week == target_week)
            .order_by(MealieMealplan.plan_date.asc(), MealieMealplan.id.asc())
        )
    )
    out: list[MealiePlanEntryOut] = []
    for p in plans:
        rec = db.get(MealieRecipe, p.mealie_recipe_id) if p.mealie_recipe_id else None
        out.append(
            MealiePlanEntryOut(
                id=p.id,
                plan_date=p.plan_date,
                iso_week=p.iso_week,
                entry_type=p.entry_type,
                title=p.title,
                recipe=_recipe_to_out(rec) if rec else None,
            )
        )
    return out


@router.get("/recipes/{mealie_id}/image")
async def get_recipe_image(mealie_id: str, db: Session = Depends(get_db)) -> Response:
    result = await get_or_fetch_recipe_image(db, mealie_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Rezeptbild nicht verfügbar.")
    content, media_type = result
    return Response(
        content=content,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.post("/recipes/{mealie_id}/rescore", response_model=MealieRecipeOut)
async def rescore_recipe(mealie_id: str, db: Session = Depends(get_db)) -> MealieRecipeOut:
    recipe = db.get(MealieRecipe, mealie_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Mealie-Rezept nicht gefunden.")
    updated = await score_single_recipe(db, recipe, force=True)
    return _recipe_to_out(updated)
