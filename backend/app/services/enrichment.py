from __future__ import annotations

import logging
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Product, SyncRun, utcnow
from app.services.llm_enrichment import LLMEnrichmentError, classify_products_batch
from app.services.openfoodfacts import lookup_product_openfoodfacts
from app.services.picnic_service import (
    fetch_article_metadata,
    get_picnic_status,
    recompute_delivery_scores,
    recompute_latest_cart_score,
)
from app.services.scoring import parse_weight_grams
from app.services.settings_store import get_effective_llm_config, is_demo_mode

logger = logging.getLogger("stats_for_picnic.enrichment")

LLM_BATCH_SIZE = 12

NON_FOOD_CATEGORY_KEYWORDS = (
    "haushalt",
    "drogerie",
    "pfand",
    "tierbedarf",
    "reinigung",
    "körperpflege",
    "hygiene",
    "waschen",
    "putzen",
    "garten",
    "non-food",
    "nonfood",
    "huishouden",
    "drogisterij",
    "dieren",
    "statiegeld",
)

NON_FOOD_NAME_KEYWORDS = (
    "spültabs",
    "geschirrspül",
    "waschmittel",
    "weichspüler",
    "küchenrolle",
    "toilettenpapier",
    "klopapier",
    "müllbeutel",
    "gefrierbeutel",
    "alufolie",
    "backpapier",
    "zahnpasta",
    "zahnbürste",
    "shampoo",
    "duschgel",
    "handseife",
    "seife",
    "deo ",
    "deodorant",
    "katzenfutter",
    "hundefutter",
    "katzenstreu",
    "pfand",
    "leergut",
    "taschentücher",
    "wattestäbchen",
    "allzweckreiniger",
    "glasreiniger",
    "wc-reiniger",
    "spülmittel",
    "windeln",
    "feuchttücher",
)


def is_obvious_non_food(name: str, picnic_category: str | None = None) -> bool:
    cat_lower = (picnic_category or "").lower()
    name_lower = (name or "").lower()
    if any(kw in cat_lower for kw in NON_FOOD_CATEGORY_KEYWORDS):
        return True
    return bool(any(kw in name_lower for kw in NON_FOOD_NAME_KEYWORDS))


async def enrich_pending_products(
    db: Session,
    *,
    limit: int = 100,
    off_client: httpx.AsyncClient | None = None,
    llm_client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Orchestrate 2-stage enrichment: Non-Food pre-filter -> OpenFoodFacts -> DeepSeek Flash batch."""
    run = SyncRun(source="enrichment", started_at=utcnow(), status="running")
    db.add(run)
    db.commit()

    stats = {
        "processed": 0,
        "rule_non_food": 0,
        "openfoodfacts": 0,
        "llm": 0,
        "skipped_manual": 0,
        "remaining_pending": 0,
    }

    try:
        pending = list(
            db.scalars(
                select(Product)
                .where(Product.enrichment_source == "pending")
                .limit(limit)
            )
        )

        llm_queue: list[Product] = []

        live_picnic_ready = not is_demo_mode(db) and get_picnic_status(db) == "ok"

        for product in pending:
            if product.manual_override:
                stats["skipped_manual"] += 1
                continue

            stats["processed"] += 1

            # One-time article metadata lookup (category + GTIN) for brand-new live Picnic products
            if live_picnic_ready and not product.picnic_category and not product.gtin:
                cat_name, gtin_val = fetch_article_metadata(db, product.picnic_id)
                if cat_name:
                    product.picnic_category = cat_name
                if gtin_val:
                    product.gtin = gtin_val

            # Stage 0: Non-food rule pre-filter (zero external API calls)
            if is_obvious_non_food(product.name, product.picnic_category):
                product.is_food = False
                product.bucket = "household"
                product.ignored = True
                product.ignored_reason = "household"
                product.enrichment_source = "rule"
                product.enrichment_confidence = 0.99
                product.enriched_at = utcnow()
                stats["rule_non_food"] += 1
                continue

            # Stage 1: OpenFoodFacts
            off_hit = await lookup_product_openfoodfacts(
                name=product.name,
                gtin=product.gtin,
                client=off_client,
            )
            if off_hit is not None:
                product.is_food = off_hit.bucket != "household"
                product.bucket = off_hit.bucket
                product.kcal_per_100g = off_hit.kcal_per_100g
                product.protein_g_per_100g = off_hit.protein_g_per_100g
                product.carbs_g_per_100g = off_hit.carbs_g_per_100g
                product.sugar_g_per_100g = off_hit.sugar_g_per_100g
                product.fat_g_per_100g = off_hit.fat_g_per_100g
                product.fiber_g_per_100g = off_hit.fiber_g_per_100g
                if off_hit.nova_group is not None:
                    product.nova_group = off_hit.nova_group
                product.nutriscore_grade = off_hit.nutriscore_grade
                if off_hit.gtin and not product.gtin:
                    product.gtin = off_hit.gtin
                product.parsed_weight_g = parse_weight_grams(
                    product.unit_quantity, product.bucket, product.name
                )
                product.enrichment_source = "openfoodfacts"
                product.enrichment_confidence = off_hit.confidence
                product.enriched_at = utcnow()
                stats["openfoodfacts"] += 1
            else:
                llm_queue.append(product)

        db.commit()

        # Stage 2: DeepSeek Flash batched fallback (10-15 products per call)
        base_url, api_key, model, use_responses = get_effective_llm_config(db)
        if llm_queue and api_key:
            for start in range(0, len(llm_queue), LLM_BATCH_SIZE):
                chunk = llm_queue[start : start + LLM_BATCH_SIZE]
                payload_items = [
                    {
                        "picnic_id": p.picnic_id,
                        "name": p.name,
                        "unit_quantity": p.unit_quantity,
                        "category": p.picnic_category,
                    }
                    for p in chunk
                ]
                try:
                    results = await classify_products_batch(
                        payload_items,
                        base_url=base_url,
                        api_key=api_key,
                        model=model,
                        use_responses_api=use_responses,
                        client=llm_client,
                    )
                except LLMEnrichmentError as exc:
                    logger.warning("LLM batch enrichment failed: %s", exc)
                    stats["remaining_pending"] += len(chunk)
                    continue

                by_id = {item.picnic_id: item for item in results}
                for product in chunk:
                    if product.manual_override:
                        stats["skipped_manual"] += 1
                        continue
                    item = by_id.get(product.picnic_id)
                    if item is None:
                        stats["remaining_pending"] += 1
                        continue
                    product.is_food = item.is_food and item.bucket != "household"
                    product.bucket = item.bucket
                    if not product.is_food:
                        product.ignored = True
                        product.ignored_reason = "household"
                    product.kcal_per_100g = item.kcal_per_100g
                    product.protein_g_per_100g = item.protein_g_per_100g
                    product.carbs_g_per_100g = item.carbs_g_per_100g
                    product.sugar_g_per_100g = item.sugar_g_per_100g
                    product.fat_g_per_100g = item.fat_g_per_100g
                    product.fiber_g_per_100g = item.fiber_g_per_100g
                    product.nova_group = item.nova_group
                    product.parsed_weight_g = parse_weight_grams(
                        product.unit_quantity, product.bucket, product.name
                    )
                    product.enrichment_source = "llm"
                    product.enrichment_confidence = item.confidence
                    product.enriched_at = utcnow()
                    stats["llm"] += 1
                db.commit()
        else:
            stats["remaining_pending"] += len(llm_queue)

        if stats["rule_non_food"] or stats["openfoodfacts"] or stats["llm"]:
            recompute_delivery_scores(db)
            recompute_latest_cart_score(db)

        run.status = "ok"
        run.finished_at = utcnow()
        run.summary = (
            f"Verarbeitet: {stats['processed']} (Regel: {stats['rule_non_food']}, "
            f"OFF: {stats['openfoodfacts']}, LLM: {stats['llm']})"
        )
        db.commit()
        return stats
    except Exception as exc:
        run.status = "error"
        run.error = str(exc)[:500]
        run.finished_at = utcnow()
        db.commit()
        raise
