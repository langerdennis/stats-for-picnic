from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger("stats_for_picnic.openfoodfacts")

OFF_USER_AGENT = "StatsForPicnic/0.1 (self-hosted; https://github.com/langerdennis/stats-for-picnic)"
OFF_FIELDS = (
    "code,product_name,product_name_de,brands,categories_tags,nova_group,"
    "nutriscore_grade,nutriments"
)

_TOKEN_RE = re.compile(r"[a-zäöüß0-9]+", re.IGNORECASE)
_STOPWORDS = {
    "bio",
    "ja",
    "picnic",
    "gut",
    "günstig",
    "rewe",
    "edeka",
    "alnatura",
    "original",
    "frisch",
    "frische",
    "frischer",
    "fein",
    "zart",
    "extra",
    "mit",
    "und",
    "der",
    "die",
    "das",
    "im",
    "in",
    "von",
    "aus",
    "glas",
    "dose",
    "beutel",
    "packung",
}


@dataclass(frozen=True)
class OpenFoodFactsResult:
    gtin: str | None
    kcal_per_100g: float
    protein_g_per_100g: float
    carbs_g_per_100g: float
    sugar_g_per_100g: float
    fat_g_per_100g: float
    fiber_g_per_100g: float
    nova_group: int | None
    nutriscore_grade: str | None
    bucket: str
    confidence: float


def _tokenize(text: str) -> set[str]:
    tokens = {t.lower() for t in _TOKEN_RE.findall(text) if len(t) >= 3}
    return {t for t in tokens if t not in _STOPWORDS and not t.isdigit()}


def _name_match_score(query_name: str, candidate_name: str) -> float:
    q_tokens = _tokenize(query_name)
    c_tokens = _tokenize(candidate_name)
    if not q_tokens or not c_tokens:
        return 0.0
    overlap = q_tokens & c_tokens
    if not overlap:
        return 0.0
    precision = len(overlap) / len(c_tokens)
    recall = len(overlap) / len(q_tokens)
    return (2 * precision * recall) / (precision + recall)


def _safe_float(d: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        val = d.get(key)
        if val is not None and val != "":
            try:
                return float(val)
            except (TypeError, ValueError):
                continue
    return None


def derive_bucket_from_off(
    categories_tags: list[str],
    name: str,
    protein: float,
    kcal: float,
    sugar: float,
    nova: int | None,
) -> str:
    cats = " ".join(c.lower() for c in categories_tags)
    lower_name = name.lower()

    if any(k in cats for k in ("beverages", "waters", "sodas", "juices", "teas", "coffees", "drinks")):
        return "beverage"
    if any(
        k in cats
        for k in (
            "snacks",
            "biscuits",
            "chocolates",
            "candies",
            "sweets",
            "confectionery",
            "chips",
            "crisps",
            "ice-creams",
            "pastries",
        )
    ):
        return "treat_snack"
    if (
        any(k in cats for k in ("fruits", "vegetables", "legumes", "berries", "salads", "herbs"))
        and nova in (1, 2, None)
        and sugar < 18.0
    ):
        return "produce"
    if any(
        k in cats
        for k in (
            "meats",
            "fishes",
            "seafood",
            "poultry",
            "eggs",
            "tofu",
            "skyr",
            "quark",
            "cottage-cheeses",
        )
    ):
        return "protein"
    if protein >= 10.0 and kcal > 0 and (protein / max(kcal, 1.0)) * 1000.0 >= 55.0:
        return "protein"
    if any(k in cats for k in ("wholemeal", "oats", "quinoa", "whole-grain")) or (
        "vollkorn" in lower_name or "hafer" in lower_name
    ):
        return "whole_food"
    if nova == 4 and sugar >= 20.0:
        return "treat_snack"
    return "staple"


def _parse_off_product(raw: dict[str, Any], query_name: str, confidence: float) -> OpenFoodFactsResult | None:
    nutriments = raw.get("nutriments") or {}
    kcal = _safe_float(nutriments, "energy-kcal_100g", "energy-kcal")
    if kcal is None:
        kj = _safe_float(nutriments, "energy-kj_100g", "energy_100g")
        if kj is not None:
            kcal = round(kj / 4.184, 1)
    protein = _safe_float(nutriments, "proteins_100g", "proteins")
    if kcal is None or protein is None:
        return None

    carbs = _safe_float(nutriments, "carbohydrates_100g", "carbohydrates") or 0.0
    sugar = _safe_float(nutriments, "sugars_100g", "sugars") or 0.0
    fat = _safe_float(nutriments, "fat_100g", "fat") or 0.0
    fiber = _safe_float(nutriments, "fiber_100g", "fiber") or 0.0

    nova_raw = raw.get("nova_group")
    nova_group: int | None = None
    if nova_raw is not None:
        try:
            n = int(nova_raw)
            if 1 <= n <= 4:
                nova_group = n
        except (TypeError, ValueError):
            pass

    nutriscore = raw.get("nutriscore_grade")
    if isinstance(nutriscore, str) and nutriscore.lower() in ("a", "b", "c", "d", "e"):
        nutriscore = nutriscore.lower()
    else:
        nutriscore = None

    cats = raw.get("categories_tags") or []
    if not isinstance(cats, list):
        cats = []
    prod_name = raw.get("product_name_de") or raw.get("product_name") or query_name

    bucket = derive_bucket_from_off(cats, str(prod_name), protein, kcal, sugar, nova_group)

    return OpenFoodFactsResult(
        gtin=str(raw.get("code")) if raw.get("code") else None,
        kcal_per_100g=round(max(0.0, kcal), 1),
        protein_g_per_100g=round(max(0.0, protein), 1),
        carbs_g_per_100g=round(max(0.0, carbs), 1),
        sugar_g_per_100g=round(max(0.0, sugar), 1),
        fat_g_per_100g=round(max(0.0, fat), 1),
        fiber_g_per_100g=round(max(0.0, fiber), 1),
        nova_group=nova_group,
        nutriscore_grade=nutriscore,
        bucket=bucket,
        confidence=round(confidence, 2),
    )


async def lookup_product_openfoodfacts(
    name: str,
    gtin: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> OpenFoodFactsResult | None:
    """Lookup a product by GTIN or conservative German name search on OpenFoodFacts."""
    close_client = client is None
    http = client or httpx.AsyncClient(
        timeout=8.0,
        headers={"User-Agent": OFF_USER_AGENT},
    )
    try:
        # 1. Exact GTIN lookup if available
        if gtin:
            clean_gtin = re.sub(r"\D+", "", gtin)
            if clean_gtin:
                url = f"https://de.openfoodfacts.org/api/v2/product/{clean_gtin}.json"
                resp = await http.get(url, params={"fields": OFF_FIELDS})
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("status") == 1 and isinstance(data.get("product"), dict):
                        parsed = _parse_off_product(data["product"], name, confidence=0.96)
                        if parsed is not None:
                            return parsed

        # 2. Conservative German search with strict token match threshold
        resp = await http.get(
            "https://de.openfoodfacts.org/cgi/search.pl",
            params={
                "search_terms": name,
                "search_simple": 1,
                "action": "process",
                "json": 1,
                "page_size": 5,
                "fields": OFF_FIELDS,
            },
        )
        if resp.status_code != 200:
            return None
        payload = resp.json()
        products = payload.get("products") or []
        best_result: OpenFoodFactsResult | None = None
        best_score = 0.0
        for candidate in products:
            if not isinstance(candidate, dict):
                continue
            cand_name = candidate.get("product_name_de") or candidate.get("product_name") or ""
            match = _name_match_score(name, str(cand_name))
            if match < 0.55:
                continue
            parsed = _parse_off_product(candidate, name, confidence=min(0.92, match))
            if parsed is not None and match > best_score:
                best_score = match
                best_result = parsed
        return best_result
    except Exception as exc:
        logger.debug("OpenFoodFacts lookup failed for '%s': %s", name, exc)
        return None
    finally:
        if close_client:
            await http.aclose()
