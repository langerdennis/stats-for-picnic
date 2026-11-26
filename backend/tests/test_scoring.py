from __future__ import annotations

import pytest

from app.services.scoring import (
    ScorableItem,
    compute_cart_quick_wins,
    compute_healthy_streak,
    compute_rolling_average_and_delta,
    parse_weight_grams,
    score_basket,
    score_recipe_from_nutrition,
)


@pytest.mark.parametrize(
    ("unit_quantity", "bucket", "name", "expected"),
    [
        ("500 g", "protein", "Skyr", 500.0),
        ("1 kg", "produce", "Äpfel", 1000.0),
        ("1,5 l", "beverage", "Cola", 1500.0),
        ("2 x 150 g", "protein", "Joghurt", 300.0),
        ("6 x 1,5 l", "beverage", "Mineralwasser", 9000.0),
        ("10 Stück", "protein", "Bio Freilandeier", 600.0),
        ("2 Stück", "produce", "Avocado", 400.0),
        ("1 Kopf", "produce", "Eisbergsalat", 350.0),
        (None, "treat_snack", "Chips", 175.0),
    ],
)
def test_parse_weight_grams(
    unit_quantity: str | None,
    bucket: str,
    name: str,
    expected: float,
) -> None:
    assert parse_weight_grams(unit_quantity, bucket, name) == pytest.approx(expected)


def _item(
    picnic_id: str,
    name: str,
    *,
    bucket: str,
    weight_g: float = 500.0,
    quantity: int = 1,
    kcal: float = 100.0,
    protein: float = 10.0,
    sugar: float = 2.0,
    nova: int = 1,
    is_food: bool = True,
    ignored: bool = False,
) -> ScorableItem:
    return ScorableItem(
        picnic_id=picnic_id,
        name=name,
        quantity=quantity,
        price_cents=250,
        unit_quantity=f"{int(weight_g)} g",
        parsed_weight_g=weight_g,
        is_food=is_food,
        ignored=ignored,
        bucket=bucket,
        kcal_per_100g=kcal,
        protein_g_per_100g=protein,
        sugar_g_per_100g=sugar,
        fiber_g_per_100g=3.0,
        nova_group=nova,
    )


def test_score_basket_healthy_vs_unhealthy() -> None:
    healthy = [
        _item("skyr", "Skyr Natur", bucket="protein", weight_g=1000, kcal=63, protein=11, sugar=4, nova=1),
        _item("lachs", "Wildlachs", bucket="protein", weight_g=500, kcal=142, protein=20, sugar=0, nova=1),
        _item("brokkoli", "Bio Brokkoli", bucket="produce", weight_g=1000, kcal=34, protein=2.8, sugar=1.7, nova=1),
        _item("spinat", "Babyspinat", bucket="produce", weight_g=500, kcal=23, protein=2.9, sugar=0.4, nova=1),
        _item("hafer", "Haferflocken", bucket="whole_food", weight_g=500, kcal=372, protein=13.5, sugar=0.7, nova=1),
    ]
    unhealthy = [
        _item("chips", "Kartoffelchips", bucket="treat_snack", weight_g=500, kcal=536, protein=6, sugar=3, nova=4),
        _item("kekse", "Schokokekse", bucket="treat_snack", weight_g=500, kcal=500, protein=6, sugar=34, nova=4),
        _item("cola", "Cola", bucket="beverage", weight_g=1500, kcal=42, protein=0, sugar=10.6, nova=4),
        _item("pizza", "TK Pizza", bucket="staple", weight_g=700, kcal=260, protein=10, sugar=4, nova=4),
    ]

    h_res = score_basket(healthy)
    u_res = score_basket(unhealthy)

    assert h_res.score >= 85
    assert u_res.score <= 35
    assert h_res.protein_per_1000_kcal > 45
    assert h_res.fresh_share_pct >= 40
    assert h_res.nova_1_2_share_pct == 100.0
    assert h_res.snack_share_pct == 0.0
    assert len(h_res.positive_drivers) >= 2
    assert len(u_res.negative_drivers) >= 2


def test_score_basket_ignores_household_and_family_flagged_items() -> None:
    base = [
        _item("skyr", "Skyr", bucket="protein", weight_g=500, kcal=63, protein=11, sugar=4, nova=1),
        _item("brokkoli", "Brokkoli", bucket="produce", weight_g=500, kcal=34, protein=2.8, sugar=1.7, nova=1),
    ]
    with_ignored = base + [
        _item("tabs", "Spültabs", bucket="household", is_food=False, ignored=True, kcal=0, protein=0, nova=4),
        _item("gummi", "Gummibärchen (Kinder)", bucket="treat_snack", ignored=True, kcal=343, protein=6, sugar=46, nova=4),
        _item("wasser", "Mineralwasser", bucket="beverage", weight_g=9000, kcal=0, protein=0, sugar=0, nova=1),
    ]

    r1 = score_basket(base)
    r2 = score_basket(with_ignored)

    assert r1.score == r2.score
    assert r1.fresh_share_pct == r2.fresh_share_pct
    assert r2.ignored_item_count == 2


def test_rolling_average_and_delta() -> None:
    avg, delta = compute_rolling_average_and_delta(78, [64, 68, 70, 72, 74, 76, 78, 74])
    assert avg == 72.0
    assert delta == 6

    avg_empty, delta_empty = compute_rolling_average_and_delta(78, [])
    assert avg_empty is None
    assert delta_empty is None


def test_score_recipe_from_nutrition() -> None:
    res = score_recipe_from_nutrition(
        {"calories": "520 kcal", "proteinContent": "41 g", "fiberContent": "10 g", "sugarContent": "5 g"},
        ingredients=["250 g Wildlachs", "300 g Brokkoli", "100 g Spinat", "1 Paprika"],
    )
    assert res is not None
    score, summary, protein_lvl, veggie_lvl, nova = res
    assert score >= 80
    assert protein_lvl == "hoch"
    assert veggie_lvl == "hoch"
    assert nova == 1
    assert "Protein" in summary

    assert score_recipe_from_nutrition({}, []) is None


def test_healthy_streak_tier_and_quick_wins() -> None:
    assert compute_healthy_streak([60, 72, 76, 80, 78], threshold=75) == 3
    assert compute_healthy_streak([80, 82, 70], threshold=75) == 0

    current_cart = [
        _item("chips", "Kartoffelchips", bucket="treat_snack", weight_g=350, kcal=536, protein=6, sugar=3, nova=4),
        _item("pasta", "Pasta", bucket="staple", weight_g=500, kcal=350, protein=11, sugar=3, nova=2),
    ]
    res = score_basket(current_cart)
    assert res.tier.goals_total == 4
    assert res.tier.goals_met < 4

    candidates = [
        _item("skyr", "Arla Skyr Natur", bucket="protein", weight_g=500, kcal=63, protein=11, sugar=4, nova=1),
        _item("brok", "Bio Brokkoli", bucket="produce", weight_g=500, kcal=34, protein=2.8, sugar=1.7, nova=1),
    ]
    wins = compute_cart_quick_wins(current_cart, candidates, max_results=3)
    assert len(wins) == 2
    assert all(w.score_delta > 0 for w in wins)
    assert all(w.projected_score > res.score for w in wins)

