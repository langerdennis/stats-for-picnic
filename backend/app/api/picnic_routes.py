from __future__ import annotations

import asyncio
import json
import math
from collections import defaultdict
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (
    CartSnapshot,
    Delivery,
    MealieMealplan,
    MealieRecipe,
    Product,
    SyncRun,
    utcnow,
)
from app.schemas import (
    BasketScoreResult,
    CartItemOut,
    CartModifyRequest,
    CartOut,
    DashboardResponse,
    DeliveryItemOut,
    DeliveryOut,
    DeliverySlotOut,
    MealiePlanEntryOut,
    MealieRecipeOut,
    PicnicSearchItemOut,
    ProductOut,
    ProductUpdateRequest,
    RestockSuggestion,
    ScoringTargets,
    StatsResponse,
    WeekTrendPoint,
)
from app.services.analytics import StatsRange, compute_household_stats
from app.services.enrichment import enrich_pending_products
from app.services.mealie_service import is_mealie_configured
from app.services.picnic_service import (
    PicnicReauthRequiredError,
    PicnicServiceError,
    get_cached_delivery_slots,
    get_or_fetch_product_image,
    get_picnic_status,
    modify_cart_product,
    product_to_scorable,
    recompute_delivery_scores,
    recompute_latest_cart_score,
    refresh_live_cart,
    search_picnic_products,
)
from app.services.scoring import (
    ScorableItem,
    compute_cart_quick_wins,
    compute_cart_remove_wins,
    compute_healthy_streak,
    compute_rolling_average_and_delta,
    iso_week_str,
    score_basket,
)
from app.services.settings_store import get_effective_scoring_targets, is_demo_mode

router = APIRouter(prefix="/api/v1", tags=["picnic"])


def _get_targets(db: Session) -> ScoringTargets:
    return ScoringTargets(**get_effective_scoring_targets(db))


def _product_image_url(picnic_id: str) -> str:
    return f"/api/v1/products/{picnic_id}/image"


def _product_to_out(p: Product) -> ProductOut:
    out = ProductOut.model_validate(p)
    out.image_url = _product_image_url(p.picnic_id)
    return out


def _build_mealie_entry_out(plan: MealieMealplan, recipe: MealieRecipe | None) -> MealiePlanEntryOut:
    rec_out = None
    if recipe is not None:
        rec_out = MealieRecipeOut(
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
    return MealiePlanEntryOut(
        id=plan.id,
        plan_date=plan.plan_date,
        iso_week=plan.iso_week,
        entry_type=plan.entry_type,
        title=plan.title,
        recipe=rec_out,
    )


def build_weekly_trend(db: Session) -> tuple[list[WeekTrendPoint], dict[str, BasketScoreResult]]:
    """Aggregate deliveries per ISO week and compute BasketScoreResult per week."""
    targets = _get_targets(db)
    deliveries = list(
        db.scalars(select(Delivery).order_by(Delivery.delivery_time.asc(), Delivery.iso_week.asc()))
    )
    grouped: dict[str, list[ScorableItem]] = defaultdict(list)
    week_order: list[str] = []

    for d in deliveries:
        if d.iso_week not in grouped:
            week_order.append(d.iso_week)
        for line in d.items:
            prod = line.product or db.get(Product, line.picnic_id)
            if prod is None:
                continue
            grouped[d.iso_week].append(product_to_scorable(prod, line.quantity, line.price_cents))

    trend: list[WeekTrendPoint] = []
    week_metrics: dict[str, BasketScoreResult] = {}
    for wk in week_order:
        metrics = score_basket(grouped[wk], targets=targets)
        week_metrics[wk] = metrics
        trend.append(
            WeekTrendPoint(
                iso_week=wk,
                score=metrics.score,
                protein_per_1000_kcal=metrics.protein_per_1000_kcal,
                fresh_share_pct=metrics.fresh_share_pct,
                nova_1_2_share_pct=metrics.nova_1_2_share_pct,
                snack_share_pct=metrics.snack_share_pct,
            )
        )
    return trend[-8:], week_metrics


def _compute_restock_suggestions(
    db: Session,
    cart_product_ids: set[str],
    *,
    recent_limit: int = 6,
    min_ratio: float = 0.5,
    max_results: int = 6,
) -> list[RestockSuggestion]:
    """Identify recurring staples purchased in >=50% of recent deliveries that are missing from the cart."""
    recent_deliveries = list(
        db.scalars(
            select(Delivery)
            .order_by(desc(Delivery.delivery_time), desc(Delivery.iso_week))
            .limit(recent_limit)
        )
    )
    checked = len(recent_deliveries)
    if checked < 2:
        return []

    min_hits = max(2, math.ceil(checked * min_ratio))
    hits_by_pid: dict[str, int] = defaultdict(int)
    for delivery in recent_deliveries:
        seen_in_delivery: set[str] = set()
        for line in delivery.items:
            if line.picnic_id not in seen_in_delivery:
                seen_in_delivery.add(line.picnic_id)
                hits_by_pid[line.picnic_id] += 1

    bucket_rank = {
        "produce": 0,
        "protein": 1,
        "whole_food": 2,
        "staple": 3,
        "beverage": 4,
        "treat_snack": 5,
    }
    candidates: list[tuple[int, int, str, RestockSuggestion]] = []
    for pid, hits in hits_by_pid.items():
        if hits < min_hits or pid in cart_product_ids:
            continue
        prod = db.get(Product, pid)
        if prod is None or not prod.is_food or prod.ignored or prod.bucket == "treat_snack":
            continue
        candidates.append(
            (
                -hits,
                bucket_rank.get(prod.bucket, 9),
                prod.name.lower(),
                RestockSuggestion(
                    picnic_id=prod.picnic_id,
                    name=prod.name,
                    unit_quantity=prod.unit_quantity,
                    bucket=prod.bucket,
                    image_url=_product_image_url(prod.picnic_id),
                    hits_in_recent_deliveries=hits,
                    recent_deliveries_checked=checked,
                ),
            )
        )

    candidates.sort(key=lambda row: (row[0], row[1], row[2]))
    return [row[3] for row in candidates[:max_results]]


def _resolve_active_slot(
    slots: list[DeliverySlotOut],
    fallback_start: datetime | None,
) -> tuple[datetime | None, datetime | None, datetime | None]:
    chosen = next((s for s in slots if s.selected), None) or (slots[0] if slots else None)
    if chosen is not None:
        return chosen.window_start, chosen.window_end, chosen.cut_off_time
    return fallback_start, None, None


def _build_cart_out(db: Session) -> CartOut:
    targets = _get_targets(db)
    snap = db.scalar(select(CartSnapshot).order_by(desc(CartSnapshot.id)).limit(1))
    trend, _ = build_weekly_trend(db)
    hist_scores = [pt.score for pt in trend]
    slots = get_cached_delivery_slots(db)

    if snap is None:
        slot_start, slot_end, slot_cutoff = _resolve_active_slot(slots, None)
        return CartOut(
            next_slot_start=slot_start,
            next_slot_end=slot_end,
            next_slot_cutoff=slot_cutoff,
            delivery_slots=slots,
            avg_8_weeks=compute_rolling_average_and_delta(None, hist_scores)[0],
            restock_suggestions=_compute_restock_suggestions(db, set()),
        )

    raw_items = json.loads(snap.items_json or "[]")
    items_out: list[CartItemOut] = []
    scorable: list[ScorableItem] = []

    for entry in raw_items:
        pid = entry["picnic_id"]
        qty = int(entry.get("quantity", 1))
        price = int(entry.get("price_cents", 0))
        prod = db.get(Product, pid)
        if prod is not None:
            scorable.append(product_to_scorable(prod, qty, price))
            items_out.append(
                CartItemOut(
                    picnic_id=pid,
                    name=prod.name,
                    quantity=qty,
                    price_cents=price,
                    unit_quantity=prod.unit_quantity,
                    bucket=prod.bucket,
                    nova_group=prod.nova_group,
                    ignored=prod.ignored,
                    is_food=prod.is_food,
                    protein_g_per_100g=prod.protein_g_per_100g,
                    kcal_per_100g=prod.kcal_per_100g,
                    image_url=_product_image_url(pid),
                )
            )
        else:
            items_out.append(
                CartItemOut(
                    picnic_id=pid,
                    name=entry.get("name", pid),
                    quantity=qty,
                    price_cents=price,
                    unit_quantity=entry.get("unit_quantity"),
                    image_url=_product_image_url(pid),
                )
            )

    metrics = score_basket(scorable, targets=targets)
    avg_8, delta = compute_rolling_average_and_delta(metrics.score, hist_scores)
    best_8 = max(hist_scores) if hist_scores else None
    is_pb = bool(best_8 is not None and snap.item_count > 0 and metrics.score >= best_8)

    candidate_prods = list(
        db.scalars(
            select(Product)
            .where(
                Product.is_food.is_(True),
                Product.ignored.is_(False),
                Product.bucket.in_(("protein", "produce", "whole_food")),
            )
            .order_by(desc(Product.purchase_count), Product.name.asc())
            .limit(24)
        )
    )
    candidate_scorable = [product_to_scorable(p, quantity=1, price_cents=250) for p in candidate_prods]
    quick_wins = compute_cart_quick_wins(scorable, candidate_scorable, max_results=3, targets=targets)
    remove_wins = compute_cart_remove_wins(scorable, max_results=2, targets=targets)
    cart_ids = {item.picnic_id for item in items_out}
    restock = _compute_restock_suggestions(db, cart_ids)
    slot_start, slot_end, slot_cutoff = _resolve_active_slot(slots, snap.next_slot_start)

    return CartOut(
        fetched_at=snap.fetched_at,
        total_price_cents=snap.total_price_cents,
        item_count=snap.item_count,
        next_slot_start=slot_start,
        next_slot_end=slot_end,
        next_slot_cutoff=slot_cutoff,
        delivery_slots=slots,
        items=items_out,
        metrics=metrics,
        delta_vs_avg=delta,
        avg_8_weeks=avg_8,
        is_personal_best=is_pb,
        quick_wins=quick_wins,
        remove_wins=remove_wins,
        restock_suggestions=restock,
    )


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(db: Session = Depends(get_db)) -> DashboardResponse:
    trend, week_metrics = build_weekly_trend(db)

    now_week = iso_week_str(datetime.now(UTC))
    if now_week in week_metrics:
        active_week = now_week
    elif trend:
        active_week = trend[-1].iso_week
    else:
        active_week = now_week

    current_metrics = week_metrics.get(active_week)
    hist_scores = [pt.score for pt in trend]
    # Compare current week against prior weeks (excluding itself when >= 2 weeks exist)
    baseline_scores = hist_scores[:-1] if len(hist_scores) >= 2 else hist_scores
    avg_8, delta = compute_rolling_average_and_delta(
        current_metrics.score if current_metrics else None,
        baseline_scores,
    )
    best_8 = max(hist_scores) if hist_scores else None
    streak = compute_healthy_streak(hist_scores, threshold=75)
    is_pb = bool(
        current_metrics is not None
        and best_8 is not None
        and len(hist_scores) >= 2
        and current_metrics.score >= best_8
    )

    pending_count = (
        db.scalar(select(func.count(Product.picnic_id)).where(Product.enrichment_source == "pending"))
        or 0
    )

    cart = _build_cart_out(db)
    plans = list(
        db.scalars(
            select(MealieMealplan)
            .where(MealieMealplan.iso_week == active_week)
            .order_by(MealieMealplan.plan_date.asc(), MealieMealplan.id.asc())
        )
    )
    mealie_entries = [
        _build_mealie_entry_out(
            p, db.get(MealieRecipe, p.mealie_recipe_id) if p.mealie_recipe_id else None
        )
        for p in plans
    ]

    last_run = db.scalar(
        select(SyncRun).where(SyncRun.status == "ok").order_by(desc(SyncRun.finished_at)).limit(1)
    )

    return DashboardResponse(
        demo_mode=is_demo_mode(db),
        picnic_status=get_picnic_status(db),
        mealie_configured=is_mealie_configured(db),
        current_week_iso=active_week,
        current_week_metrics=current_metrics,
        delta_vs_avg=delta,
        avg_8_weeks=avg_8,
        healthy_streak_weeks=streak,
        best_8_week_score=best_8,
        is_personal_best=is_pb,
        pending_enrichment_count=int(pending_count),
        trend_8_weeks=trend,
        live_cart_score=cart.metrics.score if cart.item_count > 0 else None,
        live_cart_item_count=cart.item_count,
        live_cart_total_cents=cart.total_price_cents,
        next_slot_start=cart.next_slot_start,
        next_slot_end=cart.next_slot_end,
        next_slot_cutoff=cart.next_slot_cutoff,
        delivery_slots=cart.delivery_slots,
        top_cart_quick_win=cart.quick_wins[0] if cart.quick_wins else None,
        weekly_mealie_entries=mealie_entries,
        last_sync_at=last_run.finished_at if last_run else None,
    )


@router.get("/deliveries", response_model=list[DeliveryOut])
def list_deliveries(db: Session = Depends(get_db)) -> list[DeliveryOut]:
    targets = _get_targets(db)
    deliveries = list(
        db.scalars(select(Delivery).order_by(desc(Delivery.delivery_time), desc(Delivery.iso_week)))
    )
    out: list[DeliveryOut] = []
    for d in deliveries:
        items_out: list[DeliveryItemOut] = []
        scorable: list[ScorableItem] = []
        for line in d.items:
            prod = line.product or db.get(Product, line.picnic_id)
            if prod is not None:
                scorable.append(product_to_scorable(prod, line.quantity, line.price_cents))
            items_out.append(
                DeliveryItemOut(
                    id=line.id,
                    picnic_id=line.picnic_id,
                    display_name=line.display_name,
                    quantity=line.quantity,
                    price_cents=line.price_cents,
                    unit_quantity=prod.unit_quantity if prod else None,
                    bucket=prod.bucket if prod else None,
                    nova_group=prod.nova_group if prod else None,
                    ignored=prod.ignored if prod else False,
                    is_food=prod.is_food if prod else True,
                    protein_g_per_100g=prod.protein_g_per_100g if prod else None,
                    kcal_per_100g=prod.kcal_per_100g if prod else None,
                    image_url=_product_image_url(line.picnic_id),
                )
            )
        metrics = score_basket(scorable, targets=targets)
        out.append(
            DeliveryOut(
                delivery_id=d.delivery_id,
                status=d.status,
                delivery_time=d.delivery_time,
                iso_week=d.iso_week,
                total_price_cents=d.total_price_cents,
                item_count=d.item_count,
                score=metrics.score,
                protein_per_1000_kcal=metrics.protein_per_1000_kcal,
                fresh_share_pct=metrics.fresh_share_pct,
                nova_1_2_share_pct=metrics.nova_1_2_share_pct,
                snack_share_pct=metrics.snack_share_pct,
                items=items_out,
                metrics=metrics,
            )
        )
    return out


@router.get("/stats", response_model=StatsResponse)
def get_stats(
    range: StatsRange = Query(default="90d"),
    db: Session = Depends(get_db),
) -> StatsResponse:
    return compute_household_stats(db, range_key=range)


@router.get("/picnic/search", response_model=list[PicnicSearchItemOut])
async def search_picnic(
    q: str = Query(min_length=2, max_length=100),
    db: Session = Depends(get_db),
) -> list[PicnicSearchItemOut]:
    try:
        return await asyncio.to_thread(search_picnic_products, db, q)
    except PicnicReauthRequiredError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except PicnicServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/cart", response_model=CartOut)
def get_cart(db: Session = Depends(get_db)) -> CartOut:
    return _build_cart_out(db)


@router.post("/cart/refresh", response_model=CartOut)
async def refresh_cart(db: Session = Depends(get_db)) -> CartOut:
    try:
        await asyncio.to_thread(refresh_live_cart, db)
    except PicnicReauthRequiredError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except PicnicServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _build_cart_out(db)


@router.post("/cart/add", response_model=CartOut)
async def add_to_cart(body: CartModifyRequest, db: Session = Depends(get_db)) -> CartOut:
    try:
        await asyncio.to_thread(
            modify_cart_product, db, product_id=body.product_id, count=body.count, action="add"
        )
    except PicnicReauthRequiredError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except PicnicServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _build_cart_out(db)


@router.post("/cart/remove", response_model=CartOut)
async def remove_from_cart(body: CartModifyRequest, db: Session = Depends(get_db)) -> CartOut:
    try:
        await asyncio.to_thread(
            modify_cart_product, db, product_id=body.product_id, count=body.count, action="remove"
        )
    except PicnicReauthRequiredError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except PicnicServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _build_cart_out(db)


@router.get("/staples", response_model=list[ProductOut])
def list_past_staples(
    filter: str = Query(default="all", pattern="^(all|high_protein|fresh|favorites)$"),
    q: str = Query(default=""),
    db: Session = Depends(get_db),
) -> list[ProductOut]:
    stmt = select(Product).where(Product.is_food.is_(True), Product.ignored.is_(False))
    if filter == "high_protein":
        stmt = stmt.where((Product.bucket == "protein") | (Product.protein_g_per_100g >= 12.0))
    elif filter == "fresh":
        stmt = stmt.where(Product.bucket == "produce")
    elif filter == "favorites":
        stmt = stmt.where(Product.purchase_count >= 2)

    stmt = stmt.order_by(desc(Product.purchase_count), Product.name.asc())
    products = list(db.scalars(stmt))

    if q.strip():
        needle = q.strip().lower()
        products = [p for p in products if needle in p.name.lower()]

    return [_product_to_out(p) for p in products[:40]]


@router.get("/products", response_model=list[ProductOut])
def list_products(
    q: str = Query(default=""),
    bucket: str = Query(default="all"),
    ignored: str = Query(default="all", pattern="^(all|only|exclude|pending)$"),
    db: Session = Depends(get_db),
) -> list[ProductOut]:
    stmt = select(Product).order_by(desc(Product.purchase_count), Product.name.asc())
    if bucket != "all":
        stmt = stmt.where(Product.bucket == bucket)
    if ignored == "only":
        stmt = stmt.where(Product.ignored.is_(True))
    elif ignored == "exclude":
        stmt = stmt.where(Product.ignored.is_(False))
    elif ignored == "pending":
        stmt = stmt.where(Product.enrichment_source == "pending")

    products = list(db.scalars(stmt))
    if q.strip():
        needle = q.strip().lower()
        products = [
            p
            for p in products
            if needle in p.name.lower() or needle in (p.picnic_category or "").lower()
        ]
    return [_product_to_out(p) for p in products]


@router.post("/products/enrich")
async def enrich_products_now(db: Session = Depends(get_db)) -> dict:
    stats = await enrich_pending_products(db)
    return {"status": "ok", **stats}


@router.get("/products/{picnic_id}/image")
async def get_product_image(picnic_id: str, db: Session = Depends(get_db)) -> Response:
    result = await get_or_fetch_product_image(db, picnic_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Produktbild nicht verfügbar.")
    content, media_type = result
    return Response(
        content=content,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.patch("/products/{picnic_id}", response_model=ProductOut)
def update_product(
    picnic_id: str,
    body: ProductUpdateRequest,
    db: Session = Depends(get_db),
) -> ProductOut:
    product = db.get(Product, picnic_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Produkt nicht gefunden.")

    data = body.model_dump(exclude_unset=True)
    for field, val in data.items():
        setattr(product, field, val)

    if "bucket" in data and data["bucket"] == "household":
        product.is_food = False
        if "ignored" not in data:
            product.ignored = True
            product.ignored_reason = product.ignored_reason or "household"
    elif "bucket" in data and data["bucket"] != "household" and "is_food" not in data:
        product.is_food = True

    if "ignored" in data and data["ignored"] is False and "ignored_reason" not in data:
        product.ignored_reason = None

    product.manual_override = True
    product.enrichment_source = "manual"
    product.enriched_at = utcnow()
    db.commit()
    db.refresh(product)

    recompute_delivery_scores(db)
    recompute_latest_cart_score(db)

    return _product_to_out(product)


@router.post("/products/{picnic_id}/re-enrich", response_model=ProductOut)
async def re_enrich_product(
    picnic_id: str,
    db: Session = Depends(get_db),
) -> ProductOut:
    """Reset a single product back to pending and run OpenFoodFacts / LLM enrichment immediately."""
    product = db.get(Product, picnic_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Produkt nicht gefunden.")

    product.manual_override = False
    product.enrichment_source = "pending"
    product.enriched_at = None
    db.commit()

    await enrich_pending_products(db, limit=1, picnic_ids=[picnic_id])
    db.refresh(product)
    return _product_to_out(product)
