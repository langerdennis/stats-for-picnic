from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True)
class DemoProductSpec:
    picnic_id: str
    name: str
    unit_quantity: str
    parsed_weight_g: float
    picnic_category: str
    price_cents: int
    is_food: bool
    bucket: str
    kcal_per_100g: float | None
    protein_g_per_100g: float | None
    carbs_g_per_100g: float | None
    sugar_g_per_100g: float | None
    fat_g_per_100g: float | None
    fiber_g_per_100g: float | None
    nova_group: int
    nutriscore_grade: str | None = None
    enrichment_source: str = "openfoodfacts"
    ignored: bool = False
    ignored_reason: str | None = None


DEMO_PRODUCTS: list[DemoProductSpec] = [
    DemoProductSpec("p_skyr", "Arla Skyr Natur", "500 g", 500, "Milchprodukte & Eier", 189, True, "protein", 63, 11.0, 4.0, 4.0, 0.2, 0.0, 1, "a"),
    DemoProductSpec("p_lachs", "Wildlachsfilet MSC", "250 g", 250, "Fisch & Fleisch", 549, True, "protein", 142, 20.5, 0.0, 0.0, 6.4, 0.0, 1, "a"),
    DemoProductSpec("p_haehnchen", "Bio Hähnchenbrustfilet", "400 g", 400, "Fisch & Fleisch", 699, True, "protein", 112, 23.0, 0.0, 0.0, 2.0, 0.0, 1, "a"),
    DemoProductSpec("p_eier", "Bio Freilandeier Größe M", "10 Stück", 600, "Milchprodukte & Eier", 399, True, "protein", 143, 12.6, 0.7, 0.4, 9.5, 0.0, 1, "a"),
    DemoProductSpec("p_frischkaese", "Körniger Frischkäse Fit", "200 g", 200, "Milchprodukte & Eier", 119, True, "protein", 92, 13.0, 1.5, 1.5, 4.0, 0.0, 2, "a"),
    DemoProductSpec("p_tofu", "Bio Naturtofu", "400 g", 400, "Vegetarisch & Vegan", 249, True, "protein", 138, 15.5, 1.8, 0.5, 7.8, 1.2, 1, "a"),
    DemoProductSpec("p_brokkoli", "Bio Brokkoli", "500 g", 500, "Obst & Gemüse", 229, True, "produce", 34, 2.8, 6.6, 1.7, 0.4, 2.6, 1, "a"),
    DemoProductSpec("p_spinat", "Bio Babyspinat gewaschen", "150 g", 150, "Obst & Gemüse", 199, True, "produce", 23, 2.9, 3.6, 0.4, 0.4, 2.2, 1, "a"),
    DemoProductSpec("p_tomaten", "Rispentomaten aromatisch", "500 g", 500, "Obst & Gemüse", 219, True, "produce", 18, 0.9, 3.9, 2.6, 0.2, 1.2, 1, "a"),
    DemoProductSpec("p_paprika", "Paprika Mix Ampel", "500 g", 500, "Obst & Gemüse", 249, True, "produce", 28, 1.0, 6.0, 4.2, 0.3, 2.1, 1, "a"),
    DemoProductSpec("p_aepfel", "Äpfel Elstar regional", "1 kg", 1000, "Obst & Gemüse", 279, True, "produce", 52, 0.3, 13.8, 10.4, 0.2, 2.4, 1, "a"),
    DemoProductSpec("p_bananen", "Bio Fairtrade Bananen", "5 Stück", 700, "Obst & Gemüse", 189, True, "produce", 89, 1.1, 22.8, 12.2, 0.3, 2.6, 1, "a"),
    DemoProductSpec("p_beeren", "TK Waldbeeren Mix ungezuckert", "300 g", 300, "Tiefkühl", 279, True, "produce", 46, 1.0, 8.2, 6.5, 0.4, 4.5, 1, "a"),
    DemoProductSpec("p_avocado", "Avocado Essreif", "2 Stück", 400, "Obst & Gemüse", 299, True, "produce", 160, 2.0, 8.5, 0.7, 14.7, 6.7, 1, "a"),
    DemoProductSpec("p_kichererbsen", "Bio Kichererbsen im Glas", "400 g", 400, "Konserven & Vorrat", 169, True, "produce", 128, 7.2, 18.0, 1.2, 2.4, 6.0, 1, "a"),
    DemoProductSpec("p_linsen", "Bio Rote Linsen", "500 g", 500, "Konserven & Vorrat", 229, True, "produce", 340, 24.0, 52.0, 2.0, 1.5, 11.0, 1, "a"),
    DemoProductSpec("p_hafer", "Bio Haferflocken Zart", "500 g", 500, "Frühstück & Müsli", 119, True, "whole_food", 372, 13.5, 58.7, 0.7, 7.0, 10.0, 1, "a"),
    DemoProductSpec("p_vollkornbrot", "Dinkel-Vollkornbrot geschnitten", "500 g", 500, "Brot & Backwaren", 249, True, "whole_food", 228, 8.4, 41.0, 2.8, 2.2, 7.5, 2, "a"),
    DemoProductSpec("p_quinoa", "Bio Quinoa Tricolore", "400 g", 400, "Reis & Getreide", 329, True, "whole_food", 368, 14.1, 64.2, 2.5, 6.1, 7.0, 1, "a"),
    DemoProductSpec("p_olivenoel", "Olivenöl Extra Vergine", "500 ml", 500, "Öle & Gewürze", 649, True, "staple", 824, 0.0, 0.0, 0.0, 91.6, 0.0, 2, "c"),
    DemoProductSpec("p_pasta", "Vollkorn Penne", "500 g", 500, "Pasta & Saucen", 169, True, "whole_food", 345, 13.0, 64.0, 3.2, 2.5, 8.5, 1, "a"),
    DemoProductSpec("p_pesto", "Pesto Genovese Basilikum", "190 g", 190, "Pasta & Saucen", 249, True, "staple", 415, 4.8, 6.5, 2.4, 41.0, 2.0, 3, "d", "llm"),
    DemoProductSpec("p_chips", "Kartoffelchips Ungarisch", "175 g", 175, "Snacks & Süßigkeiten", 199, True, "treat_snack", 536, 6.0, 51.0, 2.5, 33.0, 4.2, 4, "d"),
    DemoProductSpec("p_kekse", "Doppelkeks Schokolade", "250 g", 250, "Snacks & Süßigkeiten", 219, True, "treat_snack", 498, 6.4, 65.0, 34.0, 23.0, 3.1, 4, "e"),
    DemoProductSpec("p_tiefkuehlpizza", "Steinofenpizza Salami", "350 g", 350, "Tiefkühl", 349, True, "staple", 258, 10.2, 29.0, 3.8, 11.0, 2.1, 4, "d"),
    DemoProductSpec("p_cola", "Cola Original", "1,5 l", 1500, "Getränke", 149, True, "beverage", 42, 0.0, 10.6, 10.6, 0.0, 0.0, 4, "e"),
    DemoProductSpec("p_wasser", "Mineralwasser Medium", "6 x 1,5 l", 9000, "Getränke", 399, True, "beverage", 0, 0.0, 0.0, 0.0, 0.0, 0.0, 1, "a"),
    DemoProductSpec("p_gummibaeren", "Fruchtgummi Bären (Familie)", "200 g", 200, "Snacks & Süßigkeiten", 129, True, "treat_snack", 343, 6.9, 77.0, 46.0, 0.5, 0.0, 4, "e", "openfoodfacts", True, "family"),
    DemoProductSpec("p_spueltabs", "Geschirrspültabs All-in-One", "40 Stück", 700, "Haushalt & Reinigung", 599, False, "household", None, None, None, None, None, None, 4, None, "rule", True, "household"),
    DemoProductSpec("p_kuechenrolle", "Küchenrolle Recycling 3-lagig", "4 Stück", 400, "Haushalt & Reinigung", 279, False, "household", None, None, None, None, None, None, 4, None, "rule", True, "household"),
]

DEMO_PRODUCT_MAP: dict[str, DemoProductSpec] = {p.picnic_id: p for p in DEMO_PRODUCTS}


# 8 weeks of realistic orders progressing gently upward (~56 to ~82)
DEMO_WEEKLY_ORDERS: list[list[tuple[str, int]]] = [
    # 7 weeks ago (more pizza/snacks/cola -> ~54)
    [
        ("p_tiefkuehlpizza", 2),
        ("p_chips", 2),
        ("p_kekse", 2),
        ("p_cola", 1),
        ("p_pasta", 2),
        ("p_pesto", 1),
        ("p_tomaten", 1),
        ("p_bananen", 1),
        ("p_spueltabs", 1),
    ],
    # 6 weeks ago (~63)
    [
        ("p_tiefkuehlpizza", 2),
        ("p_chips", 2),
        ("p_kekse", 1),
        ("p_cola", 1),
        ("p_vollkornbrot", 1),
        ("p_pasta", 1),
        ("p_pesto", 1),
        ("p_aepfel", 1),
        ("p_eier", 1),
        ("p_gummibaeren", 1),
    ],
    # 5 weeks ago (~66)
    [
        ("p_tiefkuehlpizza", 1),
        ("p_chips", 2),
        ("p_kekse", 1),
        ("p_cola", 1),
        ("p_skyr", 1),
        ("p_hafer", 1),
        ("p_paprika", 1),
        ("p_tomaten", 1),
        ("p_pasta", 1),
        ("p_pesto", 1),
        ("p_wasser", 1),
    ],
    # 4 weeks ago (~69)
    [
        ("p_tiefkuehlpizza", 1),
        ("p_chips", 2),
        ("p_kekse", 1),
        ("p_skyr", 1),
        ("p_eier", 1),
        ("p_brokkoli", 1),
        ("p_aepfel", 1),
        ("p_vollkornbrot", 1),
        ("p_olivenoel", 1),
        ("p_pesto", 1),
        ("p_kuechenrolle", 1),
    ],
    # 3 weeks ago (~72)
    [
        ("p_tiefkuehlpizza", 1),
        ("p_chips", 1),
        ("p_kekse", 1),
        ("p_cola", 1),
        ("p_skyr", 1),
        ("p_tofu", 1),
        ("p_brokkoli", 1),
        ("p_paprika", 1),
        ("p_bananen", 1),
        ("p_hafer", 1),
        ("p_pasta", 1),
    ],
    # 2 weeks ago (~75)
    [
        ("p_tiefkuehlpizza", 1),
        ("p_chips", 1),
        ("p_kekse", 1),
        ("p_skyr", 2),
        ("p_haehnchen", 1),
        ("p_brokkoli", 1),
        ("p_tomaten", 1),
        ("p_beeren", 1),
        ("p_quinoa", 1),
        ("p_olivenoel", 1),
        ("p_pesto", 1),
        ("p_gummibaeren", 1),
    ],
    # 1 week ago (~77)
    [
        ("p_tiefkuehlpizza", 1),
        ("p_chips", 1),
        ("p_kekse", 1),
        ("p_skyr", 2),
        ("p_lachs", 1),
        ("p_eier", 1),
        ("p_brokkoli", 1),
        ("p_paprika", 1),
        ("p_aepfel", 1),
        ("p_vollkornbrot", 1),
        ("p_pasta", 1),
        ("p_olivenoel", 1),
        ("p_spueltabs", 1),
    ],
    # Current week (~80)
    [
        ("p_skyr", 2),
        ("p_lachs", 1),
        ("p_frischkaese", 1),
        ("p_brokkoli", 1),
        ("p_spinat", 1),
        ("p_tomaten", 1),
        ("p_beeren", 1),
        ("p_kichererbsen", 1),
        ("p_hafer", 1),
        ("p_vollkornbrot", 1),
        ("p_pesto", 1),
        ("p_olivenoel", 1),
        ("p_chips", 2),
        ("p_kekse", 1),
        ("p_wasser", 1),
        ("p_gummibaeren", 1),
    ],
]

# Initial live cart items for Pre-Checkout demo (~78-82, improves visibly when adding Skyr/produce)
DEMO_INITIAL_CART: list[tuple[str, int]] = [
    ("p_skyr", 1),
    ("p_lachs", 1),
    ("p_eier", 1),
    ("p_brokkoli", 1),
    ("p_paprika", 1),
    ("p_aepfel", 1),
    ("p_hafer", 1),
    ("p_vollkornbrot", 1),
    ("p_pesto", 1),
    ("p_tiefkuehlpizza", 1),
    ("p_chips", 2),
    ("p_kekse", 1),
    ("p_gummibaeren", 1),
    ("p_spueltabs", 1),
]


def get_demo_delivery_dates(reference: datetime | None = None) -> list[datetime]:
    """Return 8 weekly Saturday delivery datetimes ending in the current ISO week."""
    now = reference or datetime.now(UTC)
    # Anchor to the start of the current ISO week + 2 days (Wednesday 17:00 UTC)
    monday = now - timedelta(days=now.weekday())
    current_anchor = monday.replace(hour=17, minute=0, second=0, microsecond=0) + timedelta(days=2)
    return [current_anchor - timedelta(weeks=7 - idx) for idx in range(len(DEMO_WEEKLY_ORDERS))]
