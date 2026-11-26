from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import requests
from python_picnic_api2 import Picnic2FAError, Picnic2FARequired, PicnicAPI, PicnicAuthError
from sqlalchemy import delete, desc, func, select
from sqlalchemy.orm import Session

from app.models import (
    CartSnapshot,
    Delivery,
    DeliveryItem,
    MealieMealplan,
    MealieRecipe,
    Product,
    SyncRun,
    utcnow,
)
from app.schemas import BasketScoreResult, DeliverySlotOut, PicnicSearchItemOut, ScoringTargets
from app.services.demo_data import (
    DEMO_INITIAL_CART,
    DEMO_PRODUCT_MAP,
    DEMO_PRODUCTS,
    DEMO_WEEKLY_ORDERS,
    get_demo_delivery_dates,
)
from app.services.scoring import (
    ScorableItem,
    iso_week_str,
    parse_weight_grams,
    score_basket,
)
from app.services.settings_store import (
    KEY_PICNIC_AUTH_STATUS,
    KEY_PICNIC_AUTH_TOKEN,
    KEY_PICNIC_COUNTRY_CODE,
    KEY_PICNIC_DELIVERY_SLOTS_JSON,
    KEY_PICNIC_USERNAME,
    delete_setting,
    get_effective_scoring_targets,
    get_setting,
    is_demo_mode,
    set_setting,
)

logger = logging.getLogger("stats_for_picnic.picnic")

_sync_lock: asyncio.Lock | None = None


def get_sync_lock() -> asyncio.Lock:
    global _sync_lock
    if _sync_lock is None:
        _sync_lock = asyncio.Lock()
    return _sync_lock


class PicnicServiceError(Exception):
    """Base error for Picnic integration issues."""


class PicnicReauthRequiredError(PicnicServiceError):
    """Raised when the persisted Picnic token has expired or requires 2FA."""


@dataclass
class Pending2FASession:
    api: PicnicAPI
    country_code: str
    username: str
    created_at: datetime


# Process-local pending 2FA session (only lives during the interactive 2-step login)
_pending_2fa: Pending2FASession | None = None


def has_pending_2fa() -> bool:
    return _pending_2fa is not None


def clear_pending_2fa() -> None:
    global _pending_2fa
    _pending_2fa = None


def _get_last_response(api: Any | None) -> requests.Response | None:
    if api is None:
        return None
    sess = getattr(api, "session", None)
    return getattr(sess, "_sfp_last_response", None) if sess is not None else None


def _is_auth_failure(exc: Exception, api: Any | None = None) -> bool:
    if isinstance(exc, (PicnicAuthError, Picnic2FARequired)):
        return True
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return exc.response.status_code in (401, 403)
    last_resp = _get_last_response(api)
    if last_resp is not None and last_resp.status_code in (401, 403):
        return True
    msg = str(exc).lower()
    return "401" in msg or "unauthorized" in msg or "unauthenticated" in msg


def _build_api_client(db: Session) -> PicnicAPI:
    token = get_setting(db, KEY_PICNIC_AUTH_TOKEN)
    country_code = get_setting(db, KEY_PICNIC_COUNTRY_CODE, "DE") or "DE"
    if not token:
        raise PicnicReauthRequiredError("Picnic ist nicht verbunden. Bitte in den Einstellungen anmelden.")
    client = PicnicAPI(country_code=country_code, auth_token=token)

    def _capture_response(resp: requests.Response, *_args: Any, **_kwargs: Any) -> None:
        client.session._sfp_last_response = resp  # type: ignore[attr-defined]

    client.session.hooks["response"].append(_capture_response)
    return client


def _persist_rotated_token(db: Session, api: PicnicAPI) -> None:
    new_token = getattr(api.session, "auth_token", None)
    if new_token:
        current = get_setting(db, KEY_PICNIC_AUTH_TOKEN)
        if new_token != current:
            set_setting(db, KEY_PICNIC_AUTH_TOKEN, new_token)


def start_login(
    db: Session,
    country_code: str,
    username: str,
    password: str,
    api_factory: Any = PicnicAPI,
) -> dict[str, Any]:
    """Step 1 of Picnic login. Persists token directly or enters 2FA pending state."""
    global _pending_2fa
    clear_pending_2fa()

    api = api_factory(country_code=country_code)
    set_setting(db, KEY_PICNIC_COUNTRY_CODE, country_code)
    set_setting(db, KEY_PICNIC_USERNAME, username)

    try:
        api.login(username=username, password=password)
    except Picnic2FARequired:
        _pending_2fa = Pending2FASession(
            api=api,
            country_code=country_code,
            username=username,
            created_at=utcnow(),
        )
        set_setting(db, KEY_PICNIC_AUTH_STATUS, "2fa_pending")
        return {
            "status": "2fa_required",
            "message": "Zwei-Faktor-Authentifizierung erforderlich. Bitte Kanal wählen.",
            "channels": ["SMS", "EMAIL"],
        }
    except PicnicAuthError as exc:
        set_setting(db, KEY_PICNIC_AUTH_STATUS, "auth_failed")
        raise PicnicServiceError(f"Picnic Anmeldung fehlgeschlagen: {exc}") from exc
    except Exception as exc:
        set_setting(db, KEY_PICNIC_AUTH_STATUS, "auth_failed")
        raise PicnicServiceError(f"Verbindung zu Picnic fehlgeschlagen: {exc}") from exc

    token = getattr(api.session, "auth_token", None)
    if not token:
        set_setting(db, KEY_PICNIC_AUTH_STATUS, "auth_failed")
        raise PicnicServiceError("Picnic hat kein Auth-Token zurückgegeben.")

    set_setting(db, KEY_PICNIC_AUTH_TOKEN, token)
    set_setting(db, KEY_PICNIC_AUTH_STATUS, "ok")
    return {"status": "ok", "message": "Erfolgreich mit Picnic verbunden."}


def request_2fa_code(db: Session, channel: str = "SMS") -> dict[str, Any]:
    """Step 1b: Trigger SMS or EMAIL 2FA code using the pending Picnic session."""
    if _pending_2fa is None:
        raise PicnicServiceError("Keine aktive 2FA-Sitzung. Bitte Anmeldung neu starten.")
    try:
        _pending_2fa.api.generate_2fa_code(channel=channel)
    except Picnic2FAError as exc:
        raise PicnicServiceError(f"2FA-Code konnte nicht angefordert werden: {exc}") from exc
    except Exception as exc:
        raise PicnicServiceError(f"Fehler beim Anfordern des 2FA-Codes: {exc}") from exc

    return {
        "status": "code_sent",
        "channel": channel,
        "message": f"Bestätigungscode wurde per {channel} angefordert.",
    }


def verify_2fa_code(db: Session, code: str) -> dict[str, Any]:
    """Step 2: Verify 6-digit OTP code and persist the resulting auth_token in SQLite."""
    if _pending_2fa is None:
        raise PicnicServiceError("Keine aktive 2FA-Sitzung. Bitte Anmeldung neu starten.")

    try:
        _pending_2fa.api.verify_2fa_code(code.strip())
    except Picnic2FAError as exc:
        raise PicnicServiceError(f"Ungültiger 2FA-Code: {exc}") from exc
    except Exception as exc:
        raise PicnicServiceError(f"2FA-Prüfung fehlgeschlagen: {exc}") from exc

    token = getattr(_pending_2fa.api.session, "auth_token", None)
    if not token:
        raise PicnicServiceError("2FA bestätigt, aber kein Auth-Token erhalten.")

    set_setting(db, KEY_PICNIC_COUNTRY_CODE, _pending_2fa.country_code)
    set_setting(db, KEY_PICNIC_USERNAME, _pending_2fa.username)
    set_setting(db, KEY_PICNIC_AUTH_TOKEN, token)
    set_setting(db, KEY_PICNIC_AUTH_STATUS, "ok")
    clear_pending_2fa()
    return {"status": "ok", "message": "Picnic 2FA abgeschlossen und Sitzung gespeichert."}


def disconnect_picnic(db: Session) -> None:
    clear_pending_2fa()
    delete_setting(db, KEY_PICNIC_AUTH_TOKEN)
    set_setting(db, KEY_PICNIC_AUTH_STATUS, "not_configured")


def get_picnic_status(db: Session) -> str:
    if is_demo_mode(db):
        return "demo"
    status = get_setting(db, KEY_PICNIC_AUTH_STATUS)
    if status:
        return status
    return "ok" if get_setting(db, KEY_PICNIC_AUTH_TOKEN) else "not_configured"


# --- Parsing helpers for python-picnic-api2 v2 Pydantic models ---


def _parse_iso_datetime(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        normalized = raw.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _extract_article_quantity(article: Any) -> int:
    decorators = getattr(article, "decorators", None) or []
    for dec in decorators:
        dec_type = getattr(dec, "type", None) or (dec.get("type") if isinstance(dec, dict) else None)
        if dec_type == "QUANTITY":
            qty = getattr(dec, "quantity", None) if not isinstance(dec, dict) else dec.get("quantity")
            if isinstance(qty, int) and qty > 0:
                return qty
    return 1


def _extract_article_unit_quantity(article: Any) -> str | None:
    uq = getattr(article, "unit_quantity", None)
    if uq:
        return str(uq)
    decorators = getattr(article, "decorators", None) or []
    for dec in decorators:
        dec_type = getattr(dec, "type", None) or (dec.get("type") if isinstance(dec, dict) else None)
        if dec_type == "UNIT_QUANTITY":
            text = (
                getattr(dec, "unit_quantity_text", None)
                if not isinstance(dec, dict)
                else dec.get("unit_quantity_text")
            )
            if text:
                return str(text)
    return None


def _upsert_product_from_article(
    db: Session,
    picnic_id: str,
    name: str,
    unit_quantity: str | None,
    image_id: str | None,
    purchased_at: datetime | None = None,
    increment_purchase: int = 0,
    picnic_category: str | None = None,
) -> Product:
    product = db.get(Product, picnic_id)
    if product is None:
        product = Product(
            picnic_id=picnic_id,
            name=name,
            unit_quantity=unit_quantity,
            parsed_weight_g=parse_weight_grams(unit_quantity, "staple", name),
            picnic_category=picnic_category,
            image_id=image_id,
            is_food=True,
            bucket="staple",
            enrichment_source="pending",
            ignored=False,
            manual_override=False,
            purchase_count=max(0, increment_purchase),
            last_purchased_at=purchased_at,
        )
        db.add(product)
    else:
        if name:
            product.name = name
        if unit_quantity and not product.unit_quantity:
            product.unit_quantity = unit_quantity
            product.parsed_weight_g = parse_weight_grams(unit_quantity, product.bucket, product.name)
        if image_id and not product.image_id:
            product.image_id = image_id
        if picnic_category and not product.picnic_category:
            product.picnic_category = picnic_category
        if increment_purchase > 0:
            product.purchase_count += increment_purchase
        if purchased_at and (
            product.last_purchased_at is None
            or _as_utc(purchased_at) > _as_utc(product.last_purchased_at)
        ):
            product.last_purchased_at = purchased_at
    return product


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def product_to_scorable(product: Product, quantity: int, price_cents: int) -> ScorableItem:
    return ScorableItem(
        picnic_id=product.picnic_id,
        name=product.name,
        quantity=quantity,
        price_cents=price_cents,
        unit_quantity=product.unit_quantity,
        parsed_weight_g=product.parsed_weight_g,
        is_food=product.is_food,
        ignored=product.ignored,
        bucket=product.bucket,
        kcal_per_100g=product.kcal_per_100g,
        protein_g_per_100g=product.protein_g_per_100g,
        sugar_g_per_100g=product.sugar_g_per_100g,
        fiber_g_per_100g=product.fiber_g_per_100g,
        nova_group=product.nova_group,
    )


def recompute_product_purchase_stats(db: Session) -> None:
    """Idempotently recompute purchase_count and last_purchased_at from delivery_items."""
    rows = db.execute(
        select(
            DeliveryItem.picnic_id,
            func.coalesce(func.sum(DeliveryItem.quantity), 0),
            func.max(Delivery.delivery_time),
        )
        .join(Delivery, DeliveryItem.delivery_id == Delivery.delivery_id)
        .group_by(DeliveryItem.picnic_id)
    ).all()
    stats_by_id = {pid: (int(total_qty), last_dt) for pid, total_qty, last_dt in rows}
    for product in db.scalars(select(Product)):
        total_qty, last_dt = stats_by_id.get(product.picnic_id, (0, None))
        product.purchase_count = total_qty
        product.last_purchased_at = last_dt
    db.commit()


def _prune_old_cart_snapshots(db: Session, keep: int = 10) -> None:
    """Keep only the most recent `keep` CartSnapshot rows to prevent unbounded SQLite growth."""
    keep_ids = list(
        db.scalars(select(CartSnapshot.id).order_by(desc(CartSnapshot.id)).limit(keep))
    )
    if keep_ids:
        db.execute(delete(CartSnapshot).where(CartSnapshot.id.notin_(keep_ids)))


def recompute_delivery_scores(db: Session, delivery_id: str | None = None) -> int:
    """Recompute cached scoring metrics for one or all deliveries."""
    targets = ScoringTargets(**get_effective_scoring_targets(db))
    stmt = select(Delivery)
    if delivery_id:
        stmt = stmt.where(Delivery.delivery_id == delivery_id)
    deliveries = list(db.scalars(stmt))
    updated = 0
    for delivery in deliveries:
        scorable: list[ScorableItem] = []
        for line in delivery.items:
            product = line.product or db.get(Product, line.picnic_id)
            if product is None:
                continue
            scorable.append(product_to_scorable(product, line.quantity, line.price_cents))
        result = score_basket(scorable, targets=targets)
        delivery.score = float(result.score)
        delivery.protein_per_1000_kcal = result.protein_per_1000_kcal
        delivery.fresh_share_pct = result.fresh_share_pct
        delivery.nova_1_2_share_pct = result.nova_1_2_share_pct
        delivery.snack_share_pct = result.snack_share_pct
        updated += 1
    db.commit()
    return updated


def recompute_latest_cart_score(db: Session) -> BasketScoreResult | None:
    snap = db.scalar(select(CartSnapshot).order_by(desc(CartSnapshot.id)).limit(1))
    if snap is None:
        return None
    targets = ScoringTargets(**get_effective_scoring_targets(db))
    raw_items = json.loads(snap.items_json or "[]")
    scorable: list[ScorableItem] = []
    for entry in raw_items:
        product = db.get(Product, entry["picnic_id"])
        if product is None:
            continue
        scorable.append(
            product_to_scorable(
                product,
                quantity=int(entry.get("quantity", 1)),
                price_cents=int(entry.get("price_cents", 0)),
            )
        )
    result = score_basket(scorable, targets=targets)
    snap.computed_metrics_json = result.model_dump_json()
    db.commit()
    return result


# --- Demo Mode Seeding & Cart Simulation ---


def seed_demo_picnic_data(db: Session, force_cart: bool = False) -> dict[str, int]:
    """Seed realistic German demo products, 8 weeks of deliveries, and a live cart."""
    # 1. Seed products (preserve manual overrides if already seeded)
    for spec in DEMO_PRODUCTS:
        existing = db.get(Product, spec.picnic_id)
        if existing is None:
            db.add(
                Product(
                    picnic_id=spec.picnic_id,
                    name=spec.name,
                    unit_quantity=spec.unit_quantity,
                    parsed_weight_g=spec.parsed_weight_g,
                    picnic_category=spec.picnic_category,
                    is_food=spec.is_food,
                    bucket=spec.bucket,
                    kcal_per_100g=spec.kcal_per_100g,
                    protein_g_per_100g=spec.protein_g_per_100g,
                    carbs_g_per_100g=spec.carbs_g_per_100g,
                    sugar_g_per_100g=spec.sugar_g_per_100g,
                    fat_g_per_100g=spec.fat_g_per_100g,
                    fiber_g_per_100g=spec.fiber_g_per_100g,
                    nova_group=spec.nova_group,
                    nutriscore_grade=spec.nutriscore_grade,
                    enrichment_source=spec.enrichment_source,
                    enrichment_confidence=0.95,
                    enriched_at=utcnow(),
                    ignored=spec.ignored,
                    ignored_reason=spec.ignored_reason,
                    manual_override=False,
                    purchase_count=0,
                )
            )
    db.flush()

    # 2. Seed 8 weekly deliveries if not already present
    delivery_dates = get_demo_delivery_dates()
    deliveries_created = 0
    for idx, (dt, order_lines) in enumerate(zip(delivery_dates, DEMO_WEEKLY_ORDERS, strict=False)):
        delivery_id = f"demo-delivery-{idx + 1:02d}"
        if db.get(Delivery, delivery_id) is not None:
            continue
        total_price = 0
        total_items = 0
        delivery = Delivery(
            delivery_id=delivery_id,
            status="COMPLETED",
            delivery_time=dt,
            iso_week=iso_week_str(dt),
            total_price_cents=0,
            item_count=0,
        )
        db.add(delivery)
        db.flush()

        # Realistic historical price offsets for the earlier 4 demo weeks so price-change insights shine
        demo_early_price_offset = {
            "p_eier": -40,       # rising
            "p_olivenoel": -90,  # rising
            "p_tomaten": 30,     # cheaper recently
        }

        for pid, qty in order_lines:
            spec = DEMO_PRODUCT_MAP[pid]
            unit_cents = spec.price_cents + (demo_early_price_offset.get(pid, 0) if idx < 4 else 0)
            line_price = max(50, unit_cents) * qty
            total_price += line_price
            total_items += qty
            db.add(
                DeliveryItem(
                    delivery_id=delivery_id,
                    picnic_id=pid,
                    quantity=qty,
                    price_cents=line_price,
                    display_name=spec.name,
                )
            )
            prod = db.get(Product, pid)
            if prod is not None:
                prod.purchase_count += qty
                if prod.last_purchased_at is None or _as_utc(dt) > _as_utc(prod.last_purchased_at):
                    prod.last_purchased_at = dt

        delivery.total_price_cents = total_price
        delivery.item_count = total_items
        deliveries_created += 1

    db.commit()
    recompute_delivery_scores(db)

    # 3. Seed live cart snapshot if missing or forced
    existing_cart = db.scalar(select(CartSnapshot).order_by(desc(CartSnapshot.id)).limit(1))
    if existing_cart is None or force_cart:
        _save_demo_cart(db, DEMO_INITIAL_CART)

    return {"products": len(DEMO_PRODUCTS), "deliveries_created": deliveries_created}


def clear_demo_data(db: Session) -> dict[str, int]:
    """Remove seeded demo deliveries, demo recipes/plans, demo cart snapshots, and demo products."""
    demo_product_ids = list(DEMO_PRODUCT_MAP.keys())

    del_deliveries = db.execute(
        delete(Delivery).where(Delivery.delivery_id.like("demo-delivery-%"))
    ).rowcount or 0
    del_plans = db.execute(
        delete(MealieMealplan).where(MealieMealplan.mealie_recipe_id.like("demo-rec-%"))
    ).rowcount or 0
    del_recipes = db.execute(
        delete(MealieRecipe).where(MealieRecipe.mealie_id.like("demo-rec-%"))
    ).rowcount or 0
    del_products = db.execute(
        delete(Product).where(Product.picnic_id.in_(demo_product_ids))
    ).rowcount or 0

    # Drop cart snapshots that only contain demo products
    snaps = list(db.scalars(select(CartSnapshot)))
    del_carts = 0
    demo_id_set = set(demo_product_ids)
    for snap in snaps:
        raw_items = json.loads(snap.items_json or "[]")
        if raw_items and all(item.get("picnic_id") in demo_id_set for item in raw_items):
            db.delete(snap)
            del_carts += 1

    db.commit()
    return {
        "deliveries_removed": del_deliveries,
        "products_removed": del_products,
        "recipes_removed": del_recipes,
        "plans_removed": del_plans,
        "carts_removed": del_carts,
    }


def get_cached_delivery_slots(db: Session) -> list[DeliverySlotOut]:
    """Return cached upcoming delivery slots (selected first or chronological)."""
    raw = get_setting(db, KEY_PICNIC_DELIVERY_SLOTS_JSON, "")
    if not raw:
        return []
    try:
        items = json.loads(raw)
        if not isinstance(items, list):
            return []
    except Exception:
        return []

    now = utcnow()
    out: list[DeliverySlotOut] = []
    for entry in items:
        if not isinstance(entry, dict) or not entry.get("window_start"):
            continue
        start_dt = _parse_iso_datetime(str(entry["window_start"]))
        if start_dt is None:
            continue
        end_dt = _parse_iso_datetime(entry.get("window_end"))
        cutoff_dt = _parse_iso_datetime(entry.get("cut_off_time"))
        # Skip expired slots (allow small 1h grace window)
        if _as_utc(end_dt or start_dt) < now - timedelta(hours=1):
            continue
        out.append(
            DeliverySlotOut(
                slot_id=str(entry.get("slot_id") or ""),
                window_start=start_dt,
                window_end=end_dt,
                cut_off_time=cutoff_dt,
                is_available=bool(entry.get("is_available", True)),
                selected=bool(entry.get("selected", False)),
            )
        )
    out.sort(key=lambda s: _as_utc(s.window_start))
    return out[:6]


def _save_demo_cart(db: Session, items: list[tuple[str, int]]) -> CartSnapshot:
    serialized: list[dict[str, Any]] = []
    total_price = 0
    total_count = 0
    scorable: list[ScorableItem] = []

    for pid, qty in items:
        if qty <= 0:
            continue
        product = db.get(Product, pid)
        spec = DEMO_PRODUCT_MAP.get(pid)
        if product is None:
            continue
        unit_price = spec.price_cents if spec else 249
        line_price = unit_price * qty
        total_price += line_price
        total_count += qty
        serialized.append(
            {
                "picnic_id": pid,
                "name": product.name,
                "quantity": qty,
                "price_cents": line_price,
                "unit_quantity": product.unit_quantity,
            }
        )
        scorable.append(product_to_scorable(product, qty, line_price))

    targets = ScoringTargets(**get_effective_scoring_targets(db))
    metrics = score_basket(scorable, targets=targets)
    now = utcnow()
    demo_slot_specs = [
        (1, 18, False),
        (2, 16, True),
        (3, 10, False),
        (4, 17, False),
    ]
    demo_slots_payload = []
    next_slot = (now + timedelta(days=2)).replace(hour=16, minute=0, second=0, microsecond=0)
    for idx_s, (days_ahead, hour, is_sel) in enumerate(demo_slot_specs, start=1):
        start_dt = (now + timedelta(days=days_ahead)).replace(
            hour=hour, minute=0, second=0, microsecond=0
        )
        end_dt = start_dt + timedelta(hours=1)
        cutoff_dt = (start_dt - timedelta(days=1)).replace(hour=22, minute=0)
        if is_sel:
            next_slot = start_dt
        demo_slots_payload.append(
            {
                "slot_id": f"demo-slot-{idx_s}",
                "window_start": start_dt.isoformat(),
                "window_end": end_dt.isoformat(),
                "cut_off_time": cutoff_dt.isoformat(),
                "is_available": True,
                "selected": is_sel,
            }
        )
    set_setting(db, KEY_PICNIC_DELIVERY_SLOTS_JSON, json.dumps(demo_slots_payload))

    snap = CartSnapshot(
        fetched_at=now,
        total_price_cents=total_price,
        item_count=total_count,
        next_slot_start=next_slot,
        items_json=json.dumps(serialized),
        computed_metrics_json=metrics.model_dump_json(),
    )
    db.add(snap)
    db.flush()
    _prune_old_cart_snapshots(db)
    db.commit()
    db.refresh(snap)
    return snap


# --- Live Picnic Sync & Cart Mutations ---


def _extract_cart_snapshot(db: Session, cart: Any) -> CartSnapshot:
    items_serialized: list[dict[str, Any]] = []
    scorable: list[ScorableItem] = []
    total_count = 0

    for line in getattr(cart, "items", None) or []:
        line_price = getattr(line, "price", None) or getattr(line, "display_price", None) or 0
        for article in getattr(line, "items", None) or []:
            pid = getattr(article, "id", None)
            if not pid:
                continue
            qty = _extract_article_quantity(article)
            name = getattr(article, "name", None) or pid
            uq = _extract_article_unit_quantity(article)
            img_ids = getattr(article, "image_ids", None) or []
            img_id = img_ids[0] if img_ids else None
            price_cents = line_price if line_price else (getattr(article, "price", 0) or 0) * qty

            product = _upsert_product_from_article(
                db=db,
                picnic_id=pid,
                name=name,
                unit_quantity=uq,
                image_id=img_id,
            )
            db.flush()
            total_count += qty
            items_serialized.append(
                {
                    "picnic_id": pid,
                    "name": product.name,
                    "quantity": qty,
                    "price_cents": price_cents,
                    "unit_quantity": product.unit_quantity,
                }
            )
            scorable.append(product_to_scorable(product, qty, price_cents))

    next_slot_dt: datetime | None = None
    selected_slot = getattr(cart, "selected_slot", None)
    selected_slot_id = getattr(selected_slot, "slot_id", None) if selected_slot else None
    parsed_slots: list[dict[str, Any]] = []

    for slot in getattr(cart, "delivery_slots", None) or []:
        slot_id = str(getattr(slot, "slot_id", None) or "")
        start_dt = _parse_iso_datetime(getattr(slot, "window_start", None))
        if start_dt is None:
            continue
        end_dt = _parse_iso_datetime(getattr(slot, "window_end", None))
        cutoff_dt = _parse_iso_datetime(getattr(slot, "cut_off_time", None))
        is_avail = bool(getattr(slot, "is_available", True))
        is_sel = bool(getattr(slot, "selected", False)) or bool(
            selected_slot_id and slot_id == str(selected_slot_id)
        )
        if is_sel or is_avail:
            parsed_slots.append(
                {
                    "slot_id": slot_id,
                    "window_start": start_dt.isoformat(),
                    "window_end": end_dt.isoformat() if end_dt else None,
                    "cut_off_time": cutoff_dt.isoformat() if cutoff_dt else None,
                    "is_available": is_avail,
                    "selected": is_sel,
                }
            )
        if is_sel and next_slot_dt is None:
            next_slot_dt = start_dt

    parsed_slots.sort(key=lambda s: str(s["window_start"]))
    if next_slot_dt is None and parsed_slots:
        next_slot_dt = _parse_iso_datetime(parsed_slots[0]["window_start"])
    if parsed_slots:
        set_setting(db, KEY_PICNIC_DELIVERY_SLOTS_JSON, json.dumps(parsed_slots[:8]))

    total_price_cents = (
        getattr(cart, "checkout_total_price", None)
        or getattr(cart, "total_price", None)
        or sum(i["price_cents"] for i in items_serialized)
    )
    cart_item_count = getattr(cart, "total_count", None) or total_count
    targets = ScoringTargets(**get_effective_scoring_targets(db))
    metrics = score_basket(scorable, targets=targets)

    snap = CartSnapshot(
        fetched_at=utcnow(),
        total_price_cents=int(total_price_cents),
        item_count=int(cart_item_count),
        next_slot_start=next_slot_dt,
        items_json=json.dumps(items_serialized),
        computed_metrics_json=metrics.model_dump_json(),
    )
    db.add(snap)
    db.flush()
    _prune_old_cart_snapshots(db)
    db.commit()
    db.refresh(snap)
    return snap


def _save_empty_cart_snapshot(db: Session) -> CartSnapshot:
    """Persist an empty cart snapshot (e.g. right after an order has been submitted in Picnic)."""
    snap = CartSnapshot(
        fetched_at=utcnow(),
        total_price_cents=0,
        item_count=0,
        next_slot_start=None,
        items_json="[]",
        computed_metrics_json=BasketScoreResult(
            insight_text="Aktuell kein offener Picnic-Warenkorb."
        ).model_dump_json(),
    )
    db.add(snap)
    db.flush()
    _prune_old_cart_snapshots(db)
    db.commit()
    db.refresh(snap)
    return snap


def _format_picnic_error(exc: Exception, api: Any | None = None) -> str:
    last_resp = _get_last_response(api)
    if last_resp is not None and last_resp.status_code >= 400:
        return f"HTTP {last_resp.status_code} ({exc})"
    return str(exc)


def _fetch_cart_snapshot_safe(db: Session, client: PicnicAPI) -> CartSnapshot:
    """Fetch Picnic cart while gracefully handling empty / 204 bodies after order submission."""
    try:
        cart = client.get_cart()
        _persist_rotated_token(db, client)
        return _extract_cart_snapshot(db, cart)
    except Exception as exc:
        if _is_auth_failure(exc, client):
            raise
        is_empty_json = isinstance(exc, (json.JSONDecodeError, ValueError)) and (
            "expecting value" in str(exc).lower()
        )
        last_resp = _get_last_response(client)
        status_code = last_resp.status_code if last_resp is not None else None
        body_empty = (not last_resp.text.strip()) if last_resp is not None else True
        if is_empty_json and body_empty and (status_code is None or status_code in (200, 204, 404, 410)):
            logger.info(
                "Picnic /cart returned empty body (status=%s); treating live cart as empty.",
                status_code,
            )
            _persist_rotated_token(db, client)
            return _save_empty_cart_snapshot(db)
        raise


def sync_picnic(
    db: Session,
    api: PicnicAPI | None = None,
    max_deliveries: int = 20,
) -> dict[str, Any]:
    """Sync deliveries and live cart from Picnic (or Demo provider when DEMO_MODE=true)."""
    run = SyncRun(source="picnic", started_at=utcnow(), status="running")
    db.add(run)
    db.commit()

    client: PicnicAPI | None = None
    try:
        if is_demo_mode(db):
            seeded = seed_demo_picnic_data(db)
            run.status = "ok"
            run.finished_at = utcnow()
            run.summary = (
                f"Demo-Sync abgeschlossen ({seeded['products']} Produkte, "
                f"{seeded['deliveries_created']} neue Lieferungen)."
            )
            db.commit()
            return {"status": "ok", "mode": "demo", **seeded}

        client = api or _build_api_client(db)
        summaries = client.get_deliveries(summary=True)
        _persist_rotated_token(db, client)

        synced_deliveries = 0
        for summary in summaries[:max_deliveries]:
            delivery_id = getattr(summary, "delivery_id", None)
            if not delivery_id:
                continue
            status = getattr(summary, "status", None) or "UNKNOWN"
            if status == "CANCELLED":
                continue

            existing = db.get(Delivery, delivery_id)
            if existing is not None and existing.status == "COMPLETED" and existing.items:
                continue

            try:
                detail = client.get_delivery(delivery_id)
                _persist_rotated_token(db, client)
            except Exception as detail_exc:
                if _is_auth_failure(detail_exc, client):
                    raise
                if isinstance(detail_exc, (json.JSONDecodeError, ValueError)) and (
                    "expecting value" in str(detail_exc).lower()
                ):
                    logger.warning(
                        "Skipping delivery %s due to empty Picnic detail response (%s).",
                        delivery_id,
                        _format_picnic_error(detail_exc, client),
                    )
                    continue
                raise

            slot = getattr(detail, "slot", None) or getattr(summary, "slot", None)
            dt = (
                _parse_iso_datetime(getattr(slot, "window_start", None))
                or _parse_iso_datetime(getattr(detail, "creation_time", None))
                or utcnow()
            )
            iso_wk = iso_week_str(dt)

            if existing is None:
                delivery = Delivery(
                    delivery_id=delivery_id,
                    status=getattr(detail, "status", None) or status,
                    delivery_time=dt,
                    iso_week=iso_wk,
                    total_price_cents=0,
                    item_count=0,
                    raw_json=json.dumps(getattr(detail, "raw", {}) or {}, default=str),
                )
                db.add(delivery)
                db.flush()
            else:
                delivery = existing
                delivery.status = getattr(detail, "status", None) or status
                delivery.delivery_time = dt
                delivery.iso_week = iso_wk
                delivery.items.clear()
                db.flush()

            total_price = 0
            total_items = 0
            for order in getattr(detail, "orders", None) or []:
                order_total = getattr(order, "checkout_total_price", None) or getattr(
                    order, "total_price", None
                )
                if order_total:
                    total_price += int(order_total)
                for line in getattr(order, "items", None) or []:
                    line_price = (
                        getattr(line, "price", None) or getattr(line, "display_price", None) or 0
                    )
                    for article in getattr(line, "items", None) or []:
                        pid = getattr(article, "id", None)
                        if not pid:
                            continue
                        qty = _extract_article_quantity(article)
                        name = getattr(article, "name", None) or pid
                        uq = _extract_article_unit_quantity(article)
                        img_ids = getattr(article, "image_ids", None) or []
                        img_id = img_ids[0] if img_ids else None
                        price_cents = (
                            int(line_price)
                            if line_price
                            else int(getattr(article, "price", 0) or 0) * qty
                        )
                        _upsert_product_from_article(
                            db=db,
                            picnic_id=pid,
                            name=name,
                            unit_quantity=uq,
                            image_id=img_id,
                            purchased_at=dt,
                            increment_purchase=0,
                        )
                        db.flush()
                        db.add(
                            DeliveryItem(
                                delivery_id=delivery_id,
                                picnic_id=pid,
                                quantity=qty,
                                price_cents=price_cents,
                                display_name=name,
                            )
                        )
                        total_items += qty

            delivery.total_price_cents = total_price
            delivery.item_count = total_items
            synced_deliveries += 1

        db.commit()
        recompute_product_purchase_stats(db)
        recompute_delivery_scores(db)

        snap = _fetch_cart_snapshot_safe(db, client)

        set_setting(db, KEY_PICNIC_AUTH_STATUS, "ok")
        run.status = "ok"
        run.finished_at = utcnow()
        run.summary = (
            f"{synced_deliveries} Lieferungen synchronisiert, "
            f"Warenkorb aktualisiert ({snap.item_count} Artikel)."
        )
        db.commit()
        return {
            "status": "ok",
            "mode": "live",
            "synced_deliveries": synced_deliveries,
            "cart_item_count": snap.item_count,
        }
    except Exception as exc:
        if _is_auth_failure(exc, client):
            set_setting(db, KEY_PICNIC_AUTH_STATUS, "reauth_required")
            run.status = "reauth_required"
            run.error = "Picnic-Sitzung abgelaufen oder 2FA erneut erforderlich."
            run.finished_at = utcnow()
            db.commit()
            raise PicnicReauthRequiredError(run.error) from exc
        err_msg = _format_picnic_error(exc, client)
        run.status = "error"
        run.error = err_msg[:500]
        run.finished_at = utcnow()
        db.commit()
        raise PicnicServiceError(f"Picnic-Sync fehlgeschlagen: {err_msg}") from exc


def modify_cart_product(
    db: Session,
    product_id: str,
    count: int = 1,
    action: str = "add",
    api: PicnicAPI | None = None,
) -> CartSnapshot:
    """1-Click Re-Add or Remove item from Picnic cart and immediately refresh snapshot."""
    if is_demo_mode(db):
        snap = db.scalar(select(CartSnapshot).order_by(desc(CartSnapshot.id)).limit(1))
        if snap is None:
            seed_demo_picnic_data(db)
            snap = db.scalar(select(CartSnapshot).order_by(desc(CartSnapshot.id)).limit(1))
        current_items = json.loads(snap.items_json if snap else "[]")
        qty_map: dict[str, int] = {item["picnic_id"]: int(item["quantity"]) for item in current_items}
        if action == "add":
            qty_map[product_id] = qty_map.get(product_id, 0) + count
        else:
            new_qty = qty_map.get(product_id, 0) - count
            if new_qty <= 0:
                qty_map.pop(product_id, None)
            else:
                qty_map[product_id] = new_qty
        return _save_demo_cart(db, list(qty_map.items()))

    client = api or _build_api_client(db)
    try:
        if action == "add":
            cart = client.add_product(product_id=product_id, count=count)
        else:
            cart = client.remove_product(product_id=product_id, count=count)
        _persist_rotated_token(db, client)
        return _extract_cart_snapshot(db, cart)
    except Exception as exc:
        if _is_auth_failure(exc, client):
            set_setting(db, KEY_PICNIC_AUTH_STATUS, "reauth_required")
            raise PicnicReauthRequiredError(
                "Picnic-Sitzung abgelaufen. Bitte in den Einstellungen neu anmelden."
            ) from exc
        raise PicnicServiceError(
            f"Warenkorb-Änderung fehlgeschlagen: {_format_picnic_error(exc, client)}"
        ) from exc


def refresh_live_cart(db: Session, api: PicnicAPI | None = None) -> CartSnapshot | None:
    """Fast cart-only refresh without syncing historical deliveries or Mealie."""
    if is_demo_mode(db):
        snap = db.scalar(select(CartSnapshot).order_by(desc(CartSnapshot.id)).limit(1))
        if snap is None:
            seed_demo_picnic_data(db)
            snap = db.scalar(select(CartSnapshot).order_by(desc(CartSnapshot.id)).limit(1))
        if snap is not None:
            snap.fetched_at = utcnow()
            db.commit()
            db.refresh(snap)
        return snap

    client = api or _build_api_client(db)
    try:
        snap = _fetch_cart_snapshot_safe(db, client)
        set_setting(db, KEY_PICNIC_AUTH_STATUS, "ok")
        return snap
    except Exception as exc:
        if _is_auth_failure(exc, client):
            set_setting(db, KEY_PICNIC_AUTH_STATUS, "reauth_required")
            raise PicnicReauthRequiredError(
                "Picnic-Sitzung abgelaufen. Bitte in den Einstellungen neu anmelden."
            ) from exc
        raise PicnicServiceError(
            f"Warenkorb-Aktualisierung fehlgeschlagen: {_format_picnic_error(exc, client)}"
        ) from exc


def fetch_article_metadata(
    db: Session,
    picnic_id: str,
    api: PicnicAPI | None = None,
) -> tuple[str | None, str | None]:
    """Optional article category lookup via Picnic get_article(add_category=True)."""
    if is_demo_mode(db):
        spec = DEMO_PRODUCT_MAP.get(picnic_id)
        return (spec.picnic_category if spec else None, None)
    try:
        client = api or _build_api_client(db)
        article = client.get_article(picnic_id, add_category=True)
        _persist_rotated_token(db, client)
        if article is None:
            return None, None
        category = getattr(article, "category", None)
        cat_name = getattr(category, "name", None) if category else None
        raw = getattr(article, "raw", {}) or {}
        gtin = raw.get("gtin") or raw.get("ean")
        return cat_name, str(gtin) if gtin else None
    except Exception as exc:
        logger.debug("Optional article metadata fetch skipped for %s: %s", picnic_id, exc)
        return None, None


_BUCKET_ICON_PALETTE: dict[str, tuple[str, str]] = {
    "produce": ("#E6F2EC", "#2E7D5B"),
    "protein": ("#E5F3ED", "#1E6B4B"),
    "whole_food": ("#F3EFE6", "#786246"),
    "staple": ("#F2F1EC", "#52525B"),
    "treat_snack": ("#FEF3E2", "#B45309"),
    "beverage": ("#EAF4FB", "#0369A1"),
    "household": ("#F1F1EE", "#71717A"),
}


def _build_product_fallback_svg(name: str, bucket: str) -> bytes:
    bg, fg = _BUCKET_ICON_PALETTE.get(bucket, ("#F2F1EC", "#52525B"))
    words = [w for w in name.replace("-", " ").split() if w and w.lower() not in ("bio", "tk", "arla")]
    initials = (words[0][:2] if words else name[:2]).upper()
    safe_initials = initials.replace("&", "").replace("<", "").replace(">", "")
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96">'
        f'<rect width="96" height="96" rx="20" fill="{bg}"/>'
        f'<circle cx="48" cy="48" r="30" fill="{fg}" fill-opacity="0.10"/>'
        f'<text x="48" y="55" text-anchor="middle" '
        f'font-family="-apple-system, BlinkMacSystemFont, Inter, sans-serif" '
        f'font-size="24" font-weight="700" fill="{fg}">{safe_initials}</text>'
        f"</svg>"
    )
    return svg.encode("utf-8")


async def get_or_fetch_product_image(db: Session, picnic_id: str) -> tuple[bytes, str] | None:
    """Return disk-cached Picnic product thumbnail PNG (live) or clean bucket SVG fallback."""
    import httpx

    from app.config import get_settings

    product = db.get(Product, picnic_id)
    if product is None:
        return None

    cache_dir = get_settings().picnic_image_cache_dir
    png_path = cache_dir / f"{picnic_id}.png"
    if png_path.is_file():
        return png_path.read_bytes(), "image/png"

    if product.image_id and not is_demo_mode(db):
        country = (get_setting(db, KEY_PICNIC_COUNTRY_CODE, "DE") or "DE").lower()
        cdn_url = (
            f"https://storefront-prod.{country}.picnicinternational.com"
            f"/static/images/{product.image_id}/small.png"
        )
        try:
            async with httpx.AsyncClient(timeout=8.0) as http:
                resp = await http.get(cdn_url)
                if resp.status_code == 200 and resp.content:
                    png_path.write_bytes(resp.content)
                    return resp.content, "image/png"
        except Exception as exc:
            logger.debug("Picnic image fetch skipped for %s: %s", picnic_id, exc)

    return _build_product_fallback_svg(product.name, product.bucket), "image/svg+xml"


def search_picnic_products(
    db: Session,
    query: str,
    limit: int = 15,
    api: PicnicAPI | None = None,
) -> list[PicnicSearchItemOut]:
    """Search Picnic live catalog (or Demo catalog in DEMO_MODE) for adding items to cart."""
    needle = query.strip()
    if not needle:
        return []

    if is_demo_mode(db):
        lower_q = needle.lower()
        results: list[PicnicSearchItemOut] = []
        for spec in DEMO_PRODUCTS:
            if lower_q in spec.name.lower() or lower_q in spec.picnic_category.lower():
                existing = db.get(Product, spec.picnic_id)
                results.append(
                    PicnicSearchItemOut(
                        picnic_id=spec.picnic_id,
                        name=spec.name,
                        unit_quantity=spec.unit_quantity,
                        price_cents=spec.price_cents,
                        image_url=f"/api/v1/products/{spec.picnic_id}/image",
                        bucket=existing.bucket if existing else spec.bucket,
                        nova_group=existing.nova_group if existing else spec.nova_group,
                        in_catalog=existing is not None,
                    )
                )
        return results[:limit]

    client = api or _build_api_client(db)
    try:
        search_res = client.search(needle)
        _persist_rotated_token(db, client)
    except Exception as exc:
        if _is_auth_failure(exc):
            set_setting(db, KEY_PICNIC_AUTH_STATUS, "reauth_required")
            raise PicnicReauthRequiredError(
                "Picnic-Sitzung abgelaufen. Bitte in den Einstellungen neu anmelden."
            ) from exc
        raise PicnicServiceError(f"Picnic-Suche fehlgeschlagen: {exc}") from exc

    country = (get_setting(db, KEY_PICNIC_COUNTRY_CODE, "DE") or "DE").lower()
    out: list[PicnicSearchItemOut] = []
    for item in (getattr(search_res, "items", None) or [])[:limit]:
        pid = getattr(item, "id", None)
        name = getattr(item, "name", None)
        if not pid or not name:
            continue
        existing = db.get(Product, pid)
        img_id = getattr(item, "image_id", None)
        image_url: str | None
        if existing is not None:
            image_url = f"/api/v1/products/{pid}/image"
        elif img_id:
            image_url = (
                f"https://storefront-prod.{country}.picnicinternational.com"
                f"/static/images/{img_id}/small.png"
            )
        else:
            image_url = None
        out.append(
            PicnicSearchItemOut(
                picnic_id=pid,
                name=name,
                unit_quantity=getattr(item, "unit_quantity", None),
                price_cents=int(getattr(item, "display_price", 0) or 0),
                image_url=image_url,
                bucket=existing.bucket if existing else None,
                nova_group=existing.nova_group if existing else None,
                in_catalog=existing is not None,
            )
        )
    return out


