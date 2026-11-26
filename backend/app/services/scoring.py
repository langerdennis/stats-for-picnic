from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from app.schemas import (
    BasketScoreResult,
    CartQuickWin,
    GoalCheck,
    QualityTier,
    ScoreDriver,
    SubScores,
)

# Sensible fallback weights (grams) when unit_quantity cannot be parsed
DEFAULT_WEIGHT_BY_BUCKET: dict[str, float] = {
    "produce": 400.0,
    "protein": 300.0,
    "whole_food": 400.0,
    "staple": 400.0,
    "treat_snack": 175.0,
    "beverage": 750.0,
    "household": 500.0,
}

# Fallback macros when a product is still pending enrichment
DEFAULT_MACROS_BY_BUCKET: dict[str, tuple[float, float, float, int]] = {
    # (kcal_per_100g, protein_g_per_100g, sugar_g_per_100g, nova_group)
    "produce": (45.0, 2.0, 5.0, 1),
    "protein": (145.0, 18.0, 1.5, 1),
    "whole_food": (260.0, 9.0, 3.0, 1),
    "staple": (280.0, 8.0, 4.0, 2),
    "treat_snack": (460.0, 5.0, 32.0, 4),
    "beverage": (35.0, 0.2, 7.0, 3),
    "household": (0.0, 0.0, 0.0, 4),
}

_MULTIPACK_RE = re.compile(
    r"(\d+)\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*(kg|g|ml|cl|dl|l)\b", re.IGNORECASE
)
_WEIGHT_VOL_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kg|g|ml|cl|dl|l)\b", re.IGNORECASE)
_COUNT_RE = re.compile(
    r"(\d+)\s*(stück|st\.|stk\.?|eier|bund|kopf|köpfe|netz|packung|pack|scheiben|beutel|dose|dosen|gläser|glas|flaschen|flasche)\b",
    re.IGNORECASE,
)


def _to_float(num_str: str) -> float:
    return float(num_str.replace(",", "."))


def _unit_to_grams(value: float, unit: str) -> float:
    u = unit.lower()
    if u == "kg":
        return value * 1000.0
    if u == "g":
        return value
    if u == "l":
        return value * 1000.0
    if u == "dl":
        return value * 100.0
    if u == "cl":
        return value * 10.0
    if u == "ml":
        return value
    return value


def parse_weight_grams(
    unit_quantity: str | None,
    bucket: str | None = None,
    name: str | None = None,
) -> float:
    """Parse German/Dutch Picnic unit_quantity strings into estimated grams."""
    text = (unit_quantity or "").strip()
    if text:
        m = _MULTIPACK_RE.search(text)
        if m:
            count = int(m.group(1))
            val = _to_float(m.group(2))
            unit = m.group(3)
            grams = count * _unit_to_grams(val, unit)
            if grams > 0:
                return round(grams, 1)

        m = _WEIGHT_VOL_RE.search(text)
        if m:
            val = _to_float(m.group(1))
            unit = m.group(2)
            grams = _unit_to_grams(val, unit)
            if grams > 0:
                return round(grams, 1)

        m = _COUNT_RE.search(text)
        if m:
            count = int(m.group(1))
            unit_word = m.group(2).lower()
            lower_name = (name or "").lower()
            if "ei" in unit_word or "eier" in lower_name:
                return round(count * 60.0, 1)
            if "kopf" in unit_word or "köpfe" in unit_word:
                return round(count * 350.0, 1)
            if "bund" in unit_word:
                return round(count * 100.0, 1)
            if "netz" in unit_word:
                return round(count * 500.0, 1)
            if "scheiben" in unit_word:
                return round(count * 35.0, 1)
            if "avocado" in lower_name or "mango" in lower_name:
                return round(count * 200.0, 1)
            if "banane" in lower_name or "apfel" in lower_name or "paprika" in lower_name:
                return round(count * 140.0, 1)
            if "gurke" in lower_name or "zucchini" in lower_name:
                return round(count * 300.0, 1)
            if "brötchen" in lower_name or "brezel" in lower_name:
                return round(count * 70.0, 1)
            return round(count * 120.0, 1)

    return DEFAULT_WEIGHT_BY_BUCKET.get(bucket or "staple", 350.0)


@dataclass(frozen=True)
class ScorableItem:
    picnic_id: str
    name: str
    quantity: int
    price_cents: int
    unit_quantity: str | None
    parsed_weight_g: float | None
    is_food: bool
    ignored: bool
    bucket: str
    kcal_per_100g: float | None
    protein_g_per_100g: float | None
    sugar_g_per_100g: float | None
    fiber_g_per_100g: float | None
    nova_group: int | None


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _is_unsweetened_low_cal_beverage(item: ScorableItem, kcal: float, sugar: float) -> bool:
    return item.bucket == "beverage" and kcal <= 15.0 and sugar <= 2.0


def _is_snack_or_sugary(item: ScorableItem, sugar: float) -> bool:
    if item.bucket == "treat_snack":
        return True
    if item.bucket == "beverage" and sugar >= 5.0:
        return True
    return bool(item.bucket != "produce" and sugar >= 22.0)


def score_basket(items: list[ScorableItem]) -> BasketScoreResult:
    """Compute pure, deterministic, multi-person-safe ratios & 0-100 quality score."""
    included_count = 0
    ignored_count = 0

    total_food_weight_g = 0.0
    total_kcal = 0.0
    total_protein_g = 0.0
    fresh_weight_g = 0.0
    nova_1_2_weight_g = 0.0
    snack_weight_g = 0.0

    pos_candidates: list[tuple[float, ScoreDriver]] = []
    neg_candidates: list[tuple[float, ScoreDriver]] = []

    for item in items:
        if not item.is_food or item.ignored or item.bucket == "household":
            ignored_count += 1
            continue

        qty = max(1, item.quantity)
        included_count += 1

        default_kcal, default_protein, default_sugar, default_nova = DEFAULT_MACROS_BY_BUCKET.get(
            item.bucket, (250.0, 7.0, 5.0, 2)
        )
        kcal = item.kcal_per_100g if item.kcal_per_100g is not None else default_kcal
        protein = item.protein_g_per_100g if item.protein_g_per_100g is not None else default_protein
        sugar = item.sugar_g_per_100g if item.sugar_g_per_100g is not None else default_sugar
        nova = item.nova_group if item.nova_group is not None else default_nova

        # Unsweetened water/tea/coffee shouldn't dilute grocery produce/snack weight ratios
        if _is_unsweetened_low_cal_beverage(item, kcal, sugar):
            continue

        unit_g = item.parsed_weight_g or parse_weight_grams(
            item.unit_quantity, item.bucket, item.name
        )
        if unit_g <= 0:
            # Price-weighted fallback (~100g per EUR)
            unit_g = max(100.0, (item.price_cents / 100.0) * 100.0)

        # Cap single beverage line weight to avoid 6-pack juice dominating solid foods
        weight_g = unit_g * qty
        effective_weight_g = min(weight_g, 1500.0) if item.bucket == "beverage" else weight_g

        total_food_weight_g += effective_weight_g
        total_kcal += (effective_weight_g / 100.0) * kcal
        total_protein_g += (effective_weight_g / 100.0) * protein

        if item.bucket == "produce":
            fresh_weight_g += effective_weight_g
        if nova in (1, 2):
            nova_1_2_weight_g += effective_weight_g
        is_snack = _is_snack_or_sugary(item, sugar)
        if is_snack:
            snack_weight_g += effective_weight_g

        # Positive driver candidates
        if item.bucket == "protein" or (protein >= 10.0 and kcal > 0 and (protein / max(kcal, 1.0)) * 1000 >= 55):
            rank = effective_weight_g * (1.0 + protein / 15.0)
            pos_candidates.append(
                (
                    rank,
                    ScoreDriver(
                        picnic_id=item.picnic_id,
                        name=item.name,
                        bucket=item.bucket,
                        nova_group=nova,
                        reason=f"Starke Proteinquelle ({protein:.0f} g / 100 g)",
                        impact="positive",
                        weight_g=round(effective_weight_g, 1),
                    ),
                )
            )
        elif item.bucket == "produce":
            rank = effective_weight_g * 1.15
            pos_candidates.append(
                (
                    rank,
                    ScoreDriver(
                        picnic_id=item.picnic_id,
                        name=item.name,
                        bucket=item.bucket,
                        nova_group=nova,
                        reason="Frisches Obst / Gemüse (NOVA 1)",
                        impact="positive",
                        weight_g=round(effective_weight_g, 1),
                    ),
                )
            )
        elif item.bucket == "whole_food" and nova in (1, 2):
            rank = effective_weight_g * 0.9
            pos_candidates.append(
                (
                    rank,
                    ScoreDriver(
                        picnic_id=item.picnic_id,
                        name=item.name,
                        bucket=item.bucket,
                        nova_group=nova,
                        reason="Vollwertige Basis (NOVA 1–2)",
                        impact="positive",
                        weight_g=round(effective_weight_g, 1),
                    ),
                )
            )

        # Negative driver candidates
        if is_snack:
            rank = effective_weight_g * (1.5 if nova == 4 else 1.1)
            reason = (
                f"Snack / Süßigkeit ({sugar:.0f} g Zucker / 100 g)"
                if sugar >= 15.0
                else "Snack / Genussmittel (NOVA 4)"
            )
            neg_candidates.append(
                (
                    rank,
                    ScoreDriver(
                        picnic_id=item.picnic_id,
                        name=item.name,
                        bucket=item.bucket,
                        nova_group=nova,
                        reason=reason,
                        impact="negative",
                        weight_g=round(effective_weight_g, 1),
                    ),
                )
            )
        elif nova == 4:
            rank = effective_weight_g * 0.85
            neg_candidates.append(
                (
                    rank,
                    ScoreDriver(
                        picnic_id=item.picnic_id,
                        name=item.name,
                        bucket=item.bucket,
                        nova_group=nova,
                        reason="Stark verarbeitet (NOVA 4)",
                        impact="negative",
                        weight_g=round(effective_weight_g, 1),
                    ),
                )
            )

    if total_food_weight_g <= 0:
        return BasketScoreResult(
            score=0,
            included_item_count=included_count,
            ignored_item_count=ignored_count,
            insight_text="Noch keine auswertbaren Lebensmittel enthalten.",
        )

    protein_per_1000_kcal = (total_protein_g / total_kcal) * 1000.0 if total_kcal > 0 else 0.0
    fresh_share_pct = (fresh_weight_g / total_food_weight_g) * 100.0
    nova_1_2_share_pct = (nova_1_2_weight_g / total_food_weight_g) * 100.0
    snack_share_pct = (snack_weight_g / total_food_weight_g) * 100.0

    # Transparent sub-scores (each 0-100):
    # 1) Protein Density: 12 g -> 0, 46 g -> 100 (target ~35-45 g / 1000 kcal)
    protein_score = _clamp(((protein_per_1000_kcal - 12.0) / 34.0) * 100.0)
    # 2) Fresh & Produce Share: 0% -> 0, 42% -> 100 (target >= 35-45%)
    fresh_score = _clamp((fresh_share_pct / 42.0) * 100.0)
    # 3) Unprocessed Share (NOVA 1-2): 20% -> 0, 82% -> 100 (target >= 75%)
    nova_score = _clamp(((nova_1_2_share_pct - 20.0) / 62.0) * 100.0)
    # 4) Low Snack/Sugar Share: <= 5% -> 100, >= 45% -> 0 (target <= 15%)
    snack_score = _clamp(100.0 - ((max(0.0, snack_share_pct - 5.0)) / 40.0) * 100.0)

    combined = (
        0.30 * protein_score
        + 0.25 * fresh_score
        + 0.25 * nova_score
        + 0.20 * snack_score
    )
    final_score = int(round(_clamp(combined)))

    pos_candidates.sort(key=lambda pair: pair[0], reverse=True)
    neg_candidates.sort(key=lambda pair: pair[0], reverse=True)

    positive_drivers = [drv for _, drv in pos_candidates[:3]]
    negative_drivers = [drv for _, drv in neg_candidates[:3]]

    insight_text = _build_insight_text(
        final_score,
        protein_per_1000_kcal,
        fresh_share_pct,
        nova_1_2_share_pct,
        snack_share_pct,
    )

    tier = _build_quality_tier(
        final_score,
        protein_per_1000_kcal,
        fresh_share_pct,
        nova_1_2_share_pct,
        snack_share_pct,
    )

    return BasketScoreResult(
        score=final_score,
        protein_per_1000_kcal=round(protein_per_1000_kcal, 1),
        fresh_share_pct=round(fresh_share_pct, 1),
        nova_1_2_share_pct=round(nova_1_2_share_pct, 1),
        snack_share_pct=round(snack_share_pct, 1),
        total_food_weight_g=round(total_food_weight_g, 1),
        included_item_count=included_count,
        ignored_item_count=ignored_count,
        sub_scores=SubScores(
            protein_score=round(protein_score, 1),
            fresh_score=round(fresh_score, 1),
            nova_score=round(nova_score, 1),
            snack_score=round(snack_score, 1),
        ),
        tier=tier,
        positive_drivers=positive_drivers,
        negative_drivers=negative_drivers,
        insight_text=insight_text,
    )


def _build_quality_tier(
    score: int,
    protein_density: float,
    fresh_share: float,
    nova_1_2: float,
    snack_share: float,
) -> QualityTier:
    goals = [
        GoalCheck(
            key="protein",
            label="Protein-Ziel",
            met=protein_density >= 35.0,
            detail="≥ 35 g / 1.000 kcal",
        ),
        GoalCheck(
            key="fresh",
            label="Frisch-Ziel",
            met=fresh_share >= 35.0,
            detail="≥ 35 % Obst & Gemüse",
        ),
        GoalCheck(
            key="nova",
            label="NOVA 1–2",
            met=nova_1_2 >= 75.0,
            detail="≥ 75 % unverarbeitet",
        ),
        GoalCheck(
            key="snacks",
            label="Wenig Snacks",
            met=snack_share <= 15.0,
            detail="≤ 15 % Snacks & Zucker",
        ),
    ]
    goals_met = sum(1 for g in goals if g.met)
    if score >= 85:
        label, tone = "Spitzenklasse", "sage"
    elif score >= 75:
        label, tone = "Stark im Ziel", "sage"
    elif score >= 60:
        label, tone = "Solide Basis", "neutral"
    else:
        label, tone = "Ausbaufähig", "amber"

    return QualityTier(
        label=label,
        tone=tone,  # type: ignore[arg-type]
        goals_met=goals_met,
        goals_total=len(goals),
        goals=goals,
    )


def _build_insight_text(
    score: int,
    protein_density: float,
    fresh_share: float,
    nova_1_2: float,
    snack_share: float,
) -> str:
    if score >= 80:
        if protein_density >= 38 and fresh_share >= 35:
            return "Sehr ausgewogene Mischung mit starker Proteindichte und viel Frische."
        return "Starke Woche: hoher Anteil unverarbeiteter Lebensmittel und wenig Snacks."
    if snack_share > 20:
        return "Solide Basis, aber der Snack- und Zuckeranteil drückt den Score spürbar."
    if fresh_share < 25:
        return "Ein paar zusätzliche Portionen frisches Gemüse oder Obst heben den Score sofort."
    if protein_density < 30:
        return "Gute Frische – mit etwas mehr Protein (z. B. Skyr, Fisch, Hülsenfrüchte) noch stärker."
    if nova_1_2 < 65:
        return "Relativ viele verarbeitete Produkte – unverarbeitete Grundzutaten verbessern die Balance."
    return "Ausgeglichener Einkauf im soliden Bereich."


def compute_rolling_average_and_delta(
    current_score: int | None,
    historical_scores: list[int],
    window: int = 8,
) -> tuple[float | None, int | None]:
    """Compute rolling average over up to `window` weeks and integer delta."""
    valid = [s for s in historical_scores if s is not None]
    if not valid:
        return None, None
    window_scores = valid[-window:]
    avg = round(sum(window_scores) / len(window_scores), 1)
    if current_score is None:
        return avg, None
    return avg, round(current_score - avg)


def compute_healthy_streak(historical_scores: list[int], threshold: int = 75) -> int:
    """Count consecutive trailing weeks meeting the quality threshold."""
    streak = 0
    for s in reversed(historical_scores):
        if s >= threshold:
            streak += 1
        else:
            break
    return streak


def compute_cart_quick_wins(
    current_items: list[ScorableItem],
    candidates: list[ScorableItem],
    max_results: int = 3,
) -> list[CartQuickWin]:
    """Deterministically simulate +1 of past healthy staples to find top score boosters."""
    if not current_items or not candidates:
        return []

    base_res = score_basket(current_items)
    if base_res.score >= 98:
        return []

    in_cart_qty: dict[str, int] = {}
    for item in current_items:
        in_cart_qty[item.picnic_id] = in_cart_qty.get(item.picnic_id, 0) + item.quantity

    ranked: list[tuple[int, int, CartQuickWin]] = []
    seen_ids: set[str] = set()

    for cand in candidates:
        if cand.picnic_id in seen_ids or not cand.is_food or cand.ignored:
            continue
        if cand.bucket not in ("protein", "produce", "whole_food"):
            continue
        # Avoid suggesting items already in cart with qty >= 2
        if in_cart_qty.get(cand.picnic_id, 0) >= 2:
            continue
        seen_ids.add(cand.picnic_id)

        simulated = score_basket([*current_items, cand])
        delta = simulated.score - base_res.score
        if delta <= 0:
            continue

        if cand.bucket == "protein":
            reason = "Hebt die Proteindichte"
        elif cand.bucket == "produce":
            reason = "Erhöht den Frisch-Anteil"
        else:
            reason = "Stärkt NOVA 1–2 Anteil"

        # Prefer items not yet in cart as tie-breaker
        not_in_cart_bonus = 1 if cand.picnic_id not in in_cart_qty else 0
        ranked.append(
            (
                delta,
                not_in_cart_bonus,
                CartQuickWin(
                    picnic_id=cand.picnic_id,
                    name=cand.name,
                    bucket=cand.bucket,
                    unit_quantity=cand.unit_quantity,
                    score_delta=delta,
                    projected_score=simulated.score,
                    reason=reason,
                    image_url=f"/api/v1/products/{cand.picnic_id}/image",
                ),
            )
        )

    ranked.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [item for _, _, item in ranked[:max_results]]


def iso_week_str(dt: datetime) -> str:
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _extract_numeric(val: object) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        m = re.search(r"(\d+(?:[.,]\d+)?)", val)
        if m:
            return float(m.group(1).replace(",", "."))
    return None


def score_recipe_from_nutrition(
    nutrition: dict[str, object],
    ingredients: list[str] | None = None,
) -> tuple[int, str, str, str, int] | None:
    """Deterministically score a Mealie recipe when usable nutrition values are present.

    Returns (health_score, score_summary, protein_level, veggie_level, nova_estimate) or None.
    """
    if not nutrition:
        return None

    kcal = _extract_numeric(nutrition.get("calories"))
    protein = _extract_numeric(nutrition.get("proteinContent"))
    fiber = _extract_numeric(nutrition.get("fiberContent"))
    sugar = _extract_numeric(nutrition.get("sugarContent"))

    if kcal is None or kcal <= 0 or protein is None:
        return None

    protein_per_1000 = (protein / kcal) * 1000.0
    protein_sub = _clamp(((protein_per_1000 - 15.0) / 45.0) * 100.0)

    fiber_val = fiber if fiber is not None else 4.0
    fiber_sub = _clamp((fiber_val / 10.0) * 100.0)

    sugar_val = sugar if sugar is not None else 6.0
    sugar_sub = _clamp(100.0 - (max(0.0, sugar_val - 6.0) / 28.0) * 100.0)

    # Heuristic veggie detection from ingredients
    veggie_keywords = (
        "brokkoli",
        "spinat",
        "paprika",
        "tomate",
        "zucchini",
        "karotte",
        "möhre",
        "gurke",
        "salat",
        "bohne",
        "linse",
        "kichererbse",
        "blumenkohl",
        "pilz",
        "champignon",
        "lauch",
        "zwiebel",
        "avocado",
        "gemüse",
        "kohl",
        "erbse",
    )
    ing_text = " ".join(ingredients or []).lower()
    veggie_hits = sum(1 for kw in veggie_keywords if kw in ing_text)
    if veggie_hits >= 3 or fiber_val >= 8:
        veggie_level = "hoch"
        veggie_sub = 90.0
    elif veggie_hits >= 1 or fiber_val >= 4:
        veggie_level = "mittel"
        veggie_sub = 68.0
    else:
        veggie_level = "niedrig"
        veggie_sub = 40.0

    if protein_per_1000 >= 50:
        protein_level = "hoch"
    elif protein_per_1000 >= 30:
        protein_level = "mittel"
    else:
        protein_level = "niedrig"

    score = int(
        round(
            _clamp(
                0.40 * protein_sub + 0.25 * veggie_sub + 0.20 * fiber_sub + 0.15 * sugar_sub
            )
        )
    )
    nova_estimate = 1 if (veggie_hits >= 2 and sugar_val <= 10) else (2 if sugar_val <= 18 else 3)

    if protein_level == "hoch" and veggie_level == "hoch":
        summary = "Proteinreich & viel frisches Gemüse"
    elif protein_level == "hoch":
        summary = "Hoher Proteinanteil, gut sättigend"
    elif veggie_level == "hoch":
        summary = "Gemüsereich & ballaststoffstark"
    elif sugar_val > 20:
        summary = "Eher süßes Gericht – als gelegentliches Highlight"
    else:
        summary = "Ausgewogene Alltagsmahlzeit"

    return score, summary, protein_level, veggie_level, nova_estimate
