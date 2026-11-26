from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Delivery, Product
from app.schemas import (
    BucketSpendPoint,
    PeriodSpendScorePoint,
    PriceChangeItem,
    ProductPricePoint,
    ProductStatItem,
    ProteinValueItem,
    ShoppingHabits,
    StatsResponse,
    StatsSummary,
    WeekdayCount,
)
from app.services.scoring import parse_weight_grams

StatsRange = Literal["30d", "90d", "1y", "all"]

_GERMAN_WEEKDAYS_FULL = [
    "Montag",
    "Dienstag",
    "Mittwoch",
    "Donnerstag",
    "Freitag",
    "Samstag",
    "Sonntag",
]
_GERMAN_WEEKDAYS_SHORT = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
_GERMAN_MONTHS_SHORT = [
    "Jan",
    "Feb",
    "Mär",
    "Apr",
    "Mai",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Okt",
    "Nov",
    "Dez",
]
_HEALTHY_BUCKETS = {"produce", "protein", "whole_food"}


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _range_cutoff(range_key: StatsRange, now: datetime) -> datetime | None:
    if range_key == "30d":
        return now - timedelta(days=30)
    if range_key == "90d":
        return now - timedelta(days=90)
    if range_key == "1y":
        return now - timedelta(days=365)
    return None


def compute_household_stats(
    db: Session,
    range_key: StatsRange = "90d",
    *,
    now: datetime | None = None,
) -> StatsResponse:
    """Compute rich spending, price-history, protein-value, and shopping-habit insights."""
    ref_now = _as_utc(now) or datetime.now(UTC)
    cutoff = _range_cutoff(range_key, ref_now)

    all_deliveries = list(
        db.scalars(select(Delivery).order_by(Delivery.delivery_time.asc(), Delivery.iso_week.asc()))
    )
    deliveries: list[Delivery] = []
    for d in all_deliveries:
        dt = _as_utc(d.delivery_time)
        if cutoff is not None and dt is not None and dt < cutoff:
            continue
        deliveries.append(d)

    if not deliveries:
        return StatsResponse(
            range=range_key,
            habits=ShoppingHabits(
                weekday_distribution=[
                    WeekdayCount(day=label, count=0) for label in _GERMAN_WEEKDAYS_SHORT
                ]
            ),
        )

    # Preload products map once
    products_map: dict[str, Product] = {p.picnic_id: p for p in db.scalars(select(Product))}

    # Accumulators
    total_spend_cents = 0
    total_item_units = 0
    total_food_weight_g = 0.0
    food_spend_cents = 0
    non_food_spend_cents = 0
    healthy_food_spend_cents = 0
    snack_food_spend_cents = 0

    bucket_spend: dict[str, int] = defaultdict(int)
    bucket_weight_g: dict[str, float] = defaultdict(float)
    bucket_units: dict[str, int] = defaultdict(int)

    # Product-level accumulators
    prod_spend: dict[str, int] = defaultdict(int)
    prod_units: dict[str, int] = defaultdict(int)
    prod_hits: dict[str, int] = defaultdict(int)
    prod_weight_g: dict[str, float] = defaultdict(float)
    prod_name: dict[str, str] = {}
    prod_price_points: dict[str, list[ProductPricePoint]] = defaultdict(list)

    # Period grouping: weekly for <= 12 unique weeks, monthly for longer ranges
    unique_weeks = {d.iso_week for d in deliveries}
    group_monthly = range_key in ("1y", "all") and len(unique_weeks) > 12

    period_order: list[str] = []
    period_labels: dict[str, str] = {}
    period_spend: dict[str, int] = defaultdict(int)
    period_deliveries: dict[str, int] = defaultdict(int)
    period_scores: dict[str, list[float]] = defaultdict(list)

    delivery_dates_sorted: list[datetime] = []
    delivery_totals: list[int] = []
    weekday_counts = [0] * 7
    scores_all: list[float] = []

    for d in deliveries:
        dt = _as_utc(d.delivery_time)
        date_iso = dt.strftime("%Y-%m-%d") if dt is not None else d.iso_week
        if dt is not None:
            delivery_dates_sorted.append(dt)
            weekday_counts[dt.weekday()] += 1

        # Period key & human label
        if group_monthly and dt is not None:
            p_key = dt.strftime("%Y-%m")
            p_label = f"{_GERMAN_MONTHS_SHORT[dt.month - 1]} {str(dt.year)[2:]}"
        else:
            p_key = d.iso_week
            p_label = f"KW {d.iso_week.split('-W')[-1]}" if "-W" in d.iso_week else d.iso_week

        if p_key not in period_labels:
            period_order.append(p_key)
            period_labels[p_key] = p_label

        d_spend_from_lines = 0
        seen_in_delivery: set[str] = set()

        for line in d.items:
            qty = max(1, int(line.quantity or 1))
            line_cents = max(0, int(line.price_cents or 0))
            d_spend_from_lines += line_cents
            total_item_units += qty

            prod = products_map.get(line.picnic_id)
            bucket = prod.bucket if prod is not None else "staple"
            is_food = prod.is_food if prod is not None else (bucket != "household")
            weight_per_unit = (
                prod.parsed_weight_g
                if (prod is not None and prod.parsed_weight_g and prod.parsed_weight_g > 0)
                else parse_weight_grams(
                    prod.unit_quantity if prod else None,
                    bucket,
                    line.display_name,
                )
            )
            line_weight_g = weight_per_unit * qty

            bucket_spend[bucket] += line_cents
            bucket_weight_g[bucket] += line_weight_g
            bucket_units[bucket] += qty

            if is_food and bucket != "household":
                food_spend_cents += line_cents
                total_food_weight_g += line_weight_g
                if bucket in _HEALTHY_BUCKETS:
                    healthy_food_spend_cents += line_cents
                elif bucket == "treat_snack":
                    snack_food_spend_cents += line_cents
            else:
                non_food_spend_cents += line_cents

            pid = line.picnic_id
            prod_spend[pid] += line_cents
            prod_units[pid] += qty
            prod_weight_g[pid] += line_weight_g
            prod_name[pid] = prod.name if prod is not None else line.display_name
            if pid not in seen_in_delivery:
                seen_in_delivery.add(pid)
                prod_hits[pid] += 1

            unit_price = round(line_cents / qty) if line_cents > 0 else 0
            if unit_price > 0:
                prod_price_points[pid].append(
                    ProductPricePoint(date=date_iso, unit_price_cents=unit_price)
                )

        effective_d_spend = d.total_price_cents if d.total_price_cents > 0 else d_spend_from_lines
        total_spend_cents += effective_d_spend
        delivery_totals.append(effective_d_spend)
        period_spend[p_key] += effective_d_spend
        period_deliveries[p_key] += 1
        if d.score is not None:
            scores_all.append(float(d.score))
            period_scores[p_key].append(float(d.score))

    # Summary metrics
    delivery_count = len(deliveries)
    avg_spend_per_delivery = round(total_spend_cents / delivery_count) if delivery_count else 0
    avg_spend_per_week = round(total_spend_cents / max(1, len(unique_weeks)))
    avg_score = round(sum(scores_all) / len(scores_all)) if scores_all else None

    healthy_spend_pct = (
        round((healthy_food_spend_cents / food_spend_cents) * 100.0, 1)
        if food_spend_cents > 0
        else 0.0
    )
    snack_spend_pct = (
        round((snack_food_spend_cents / food_spend_cents) * 100.0, 1)
        if food_spend_cents > 0
        else 0.0
    )

    repeat_units = sum(units for pid, units in prod_units.items() if prod_hits[pid] >= 2)
    repeat_share_pct = (
        round((repeat_units / total_item_units) * 100.0, 1) if total_item_units > 0 else 0.0
    )

    summary = StatsSummary(
        delivery_count=delivery_count,
        total_spend_cents=total_spend_cents,
        avg_spend_per_delivery_cents=avg_spend_per_delivery,
        avg_spend_per_week_cents=avg_spend_per_week,
        total_item_units=total_item_units,
        unique_products=len(prod_spend),
        total_food_weight_kg=round(total_food_weight_g / 1000.0, 1),
        avg_score=avg_score,
        healthy_spend_share_pct=healthy_spend_pct,
        snack_spend_share_pct=snack_spend_pct,
        food_spend_cents=food_spend_cents,
        non_food_spend_cents=non_food_spend_cents,
        repeat_purchase_share_pct=repeat_share_pct,
    )

    # Buckets breakdown (sorted by spend descending)
    total_bucket_cents = sum(bucket_spend.values()) or 1
    buckets = [
        BucketSpendPoint(
            bucket=b,
            spend_cents=cents,
            share_pct=round((cents / total_bucket_cents) * 100.0, 1),
            weight_kg=round(bucket_weight_g[b] / 1000.0, 1),
            unit_count=bucket_units[b],
        )
        for b, cents in sorted(bucket_spend.items(), key=lambda kv: kv[1], reverse=True)
        if cents > 0
    ]

    # Periods trend
    periods = [
        PeriodSpendScorePoint(
            period_key=pk,
            label=period_labels[pk],
            spend_cents=period_spend[pk],
            delivery_count=period_deliveries[pk],
            avg_score=(
                round(sum(period_scores[pk]) / len(period_scores[pk]))
                if period_scores[pk]
                else None
            ),
        )
        for pk in period_order
    ]

    # Product stats + price changes + protein value leaders
    product_stats: list[ProductStatItem] = []
    price_changes: list[PriceChangeItem] = []
    protein_leaders: list[ProteinValueItem] = []

    for pid, spend in prod_spend.items():
        prod = products_map.get(pid)
        units = prod_units[pid]
        bucket = prod.bucket if prod is not None else "staple"
        name = prod_name[pid]
        image_url = f"/api/v1/products/{pid}/image"
        avg_unit_price = round(spend / max(1, units))
        history = prod_price_points.get(pid, [])
        latest_price = history[-1].unit_price_cents if history else avg_unit_price

        price_change_pct: float | None = None
        if len(history) >= 2 and history[0].unit_price_cents > 0:
            first_p = history[0].unit_price_cents
            last_p = history[-1].unit_price_cents
            delta_c = last_p - first_p
            delta_pct = round((delta_c / first_p) * 100.0, 1)
            price_change_pct = delta_pct
            if abs(delta_pct) >= 3.0 and abs(delta_c) >= 10:
                price_changes.append(
                    PriceChangeItem(
                        picnic_id=pid,
                        name=name,
                        bucket=bucket,
                        image_url=image_url,
                        first_price_cents=first_p,
                        latest_price_cents=last_p,
                        delta_cents=delta_c,
                        delta_pct=delta_pct,
                        first_date=history[0].date,
                        latest_date=history[-1].date,
                        price_history=history,
                    )
                )

        # Exclude one-off purchases (only 1 delivery) from recurring product statistics when >= 2 deliveries exist
        min_required_hits = 2 if delivery_count >= 2 else 1
        if prod_hits[pid] < min_required_hits:
            continue

        product_stats.append(
            ProductStatItem(
                picnic_id=pid,
                name=name,
                bucket=bucket,
                unit_quantity=prod.unit_quantity if prod else None,
                image_url=image_url,
                total_spend_cents=spend,
                total_units=units,
                delivery_hits=prod_hits[pid],
                total_weight_kg=round(prod_weight_g[pid] / 1000.0, 2),
                avg_unit_price_cents=avg_unit_price,
                latest_unit_price_cents=latest_price,
                price_change_pct=price_change_pct,
                price_history=history,
            )
        )

        # Protein per Euro (g protein per 1.00 EUR) for recurring, non-ignored foods with protein >= 8g/100g
        if (
            prod is not None
            and prod.is_food
            and not prod.ignored
            and prod.bucket != "household"
            and prod.protein_g_per_100g is not None
            and prod.protein_g_per_100g >= 8.0
            and avg_unit_price > 0
        ):
            unit_w = (
                prod.parsed_weight_g
                if (prod.parsed_weight_g and prod.parsed_weight_g > 0)
                else parse_weight_grams(prod.unit_quantity, prod.bucket, prod.name)
            )
            protein_per_unit = (unit_w / 100.0) * prod.protein_g_per_100g
            protein_per_eur = protein_per_unit / (avg_unit_price / 100.0)
            if protein_per_eur > 0:
                protein_leaders.append(
                    ProteinValueItem(
                        picnic_id=pid,
                        name=name,
                        bucket=bucket,
                        image_url=image_url,
                        protein_g_per_euro=round(protein_per_eur, 1),
                        protein_g_per_unit=round(protein_per_unit, 1),
                        avg_unit_price_cents=avg_unit_price,
                        total_units=units,
                    )
                )

    product_stats.sort(key=lambda item: (-item.total_spend_cents, -item.total_units, item.name))
    price_changes.sort(key=lambda item: (-abs(item.delta_pct), -abs(item.delta_cents)))
    protein_leaders.sort(key=lambda item: (-item.protein_g_per_euro, -item.total_units))

    # Shopping habits & "Wrapped" superlatives (recurring items only)
    avg_days: float | None = None
    if len(delivery_dates_sorted) >= 2:
        delivery_dates_sorted.sort()
        gaps = [
            (delivery_dates_sorted[i] - delivery_dates_sorted[i - 1]).total_seconds() / 86400.0
            for i in range(1, len(delivery_dates_sorted))
        ]
        avg_days = round(sum(gaps) / len(gaps), 1)

    fav_weekday: str | None = None
    if any(weekday_counts):
        max_idx = max(range(7), key=lambda idx: weekday_counts[idx])
        fav_weekday = _GERMAN_WEEKDAYS_FULL[max_idx]

    food_products = [p for p in product_stats if p.bucket != "household"]
    heaviest = max(food_products, key=lambda p: p.total_weight_kg, default=None)
    most_bought = max(food_products, key=lambda p: p.total_units, default=None)

    habits = ShoppingHabits(
        avg_days_between_deliveries=avg_days,
        favorite_weekday=fav_weekday,
        weekday_distribution=[
            WeekdayCount(day=_GERMAN_WEEKDAYS_SHORT[i], count=weekday_counts[i]) for i in range(7)
        ],
        largest_delivery_cents=max(delivery_totals) if delivery_totals else 0,
        smallest_delivery_cents=min(delivery_totals) if delivery_totals else 0,
        heaviest_product_name=heaviest.name if heaviest else None,
        heaviest_product_kg=round(heaviest.total_weight_kg, 1) if heaviest else 0.0,
        most_bought_product_name=most_bought.name if most_bought else None,
        most_bought_product_units=most_bought.total_units if most_bought else 0,
    )

    return StatsResponse(
        range=range_key,
        summary=summary,
        buckets=buckets,
        periods=periods,
        products=product_stats,
        price_changes=price_changes[:8],
        protein_value_leaders=protein_leaders[:6],
        habits=habits,
    )
