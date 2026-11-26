from __future__ import annotations

import json
import logging
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.schemas import (
    LLMProductBatchResponse,
    LLMProductClassification,
    LLMRecipeScoreResponse,
)

logger = logging.getLogger("stats_for_picnic.llm")

TModel = TypeVar("TModel", bound=BaseModel)

PRODUCT_BATCH_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["products"],
    "properties": {
        "products": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "picnic_id",
                    "is_food",
                    "bucket",
                    "kcal_per_100g",
                    "protein_g_per_100g",
                    "carbs_g_per_100g",
                    "sugar_g_per_100g",
                    "fat_g_per_100g",
                    "fiber_g_per_100g",
                    "nova_group",
                    "confidence",
                ],
                "properties": {
                    "picnic_id": {"type": "string"},
                    "is_food": {"type": "boolean"},
                    "bucket": {
                        "type": "string",
                        "enum": [
                            "produce",
                            "protein",
                            "whole_food",
                            "staple",
                            "treat_snack",
                            "beverage",
                            "household",
                        ],
                    },
                    "kcal_per_100g": {"type": "number"},
                    "protein_g_per_100g": {"type": "number"},
                    "carbs_g_per_100g": {"type": "number"},
                    "sugar_g_per_100g": {"type": "number"},
                    "fat_g_per_100g": {"type": "number"},
                    "fiber_g_per_100g": {"type": "number"},
                    "nova_group": {"type": "integer", "minimum": 1, "maximum": 4},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                },
            },
        }
    },
}

RECIPE_SCORE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "health_score",
        "score_summary",
        "protein_level",
        "veggie_level",
        "nova_estimate",
    ],
    "properties": {
        "health_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "score_summary": {"type": "string"},
        "protein_level": {"type": "string", "enum": ["niedrig", "mittel", "hoch"]},
        "veggie_level": {"type": "string", "enum": ["niedrig", "mittel", "hoch"]},
        "nova_estimate": {"type": "integer", "minimum": 1, "maximum": 4},
    },
}


class LLMEnrichmentError(Exception):
    """Raised when an LLM enrichment call cannot produce valid structured JSON."""


def _is_deepseek_endpoint(base_url: str, model: str) -> bool:
    return "deepseek" in base_url.lower() or "deepseek" in model.lower()


def _extract_responses_api_text(data: dict[str, Any]) -> str:
    if isinstance(data.get("output_text"), str) and data["output_text"].strip():
        return data["output_text"]
    output = data.get("output") or []
    parts: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "message":
            for content in item.get("content") or []:
                if isinstance(content, dict) and isinstance(content.get("text"), str):
                    parts.append(content["text"])
        elif isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "\n".join(parts)


def _extract_chat_completions_text(data: dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        return ""
    msg = choices[0].get("message") or {}
    content = msg.get("content")
    return content if isinstance(content, str) else ""


def _parse_json_model[TModel: BaseModel](raw_text: str, model_cls: type[TModel]) -> TModel:
    if not raw_text or not raw_text.strip():
        raise LLMEnrichmentError("LLM returned empty or whitespace-only JSON content")
    cleaned = raw_text.strip()
    # Strip accidental markdown code fences if a generic OpenAI-compatible provider adds them
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if len(lines) >= 3 and lines[-1].strip().startswith("```"):
            cleaned = "\n".join(lines[1:-1]).strip()
    try:
        parsed_obj = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LLMEnrichmentError(f"Invalid JSON from LLM: {exc}") from exc
    try:
        return model_cls.model_validate(parsed_obj)
    except ValidationError as exc:
        raise LLMEnrichmentError(f"Schema validation failed: {exc}") from exc


async def _call_responses_api(
    http: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    schema_name: str,
    json_schema: dict[str, Any],
) -> str:
    url = f"{base_url.rstrip('/')}/v1/responses"
    payload: dict[str, Any] = {
        "model": model,
        "instructions": system_prompt,
        "input": user_prompt,
        "temperature": 0.1,
        "text": {
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "strict": True,
                "schema": json_schema,
            }
        },
    }
    if _is_deepseek_endpoint(base_url, model):
        payload["thinking"] = {"type": "disabled"}

    resp = await http.post(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
    )
    resp.raise_for_status()
    return _extract_responses_api_text(resp.json())


async def _call_chat_completions_api(
    http: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
) -> str:
    url = f"{base_url.rstrip('/')}/v1/chat/completions"
    payload: dict[str, Any] = {
        "model": model,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    if _is_deepseek_endpoint(base_url, model):
        payload["thinking"] = {"type": "disabled"}

    resp = await http.post(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
    )
    resp.raise_for_status()
    return _extract_chat_completions_text(resp.json())


async def _structured_llm_call[TModel: BaseModel](
    *,
    base_url: str,
    api_key: str,
    model: str,
    use_responses_api: bool,
    system_prompt: str,
    user_prompt: str,
    schema_name: str,
    json_schema: dict[str, Any],
    model_cls: type[TModel],
    client: httpx.AsyncClient | None = None,
) -> TModel:
    if not api_key:
        raise LLMEnrichmentError("LLM_API_KEY is not configured")

    close_client = client is None
    http = client or httpx.AsyncClient(timeout=35.0)
    last_error: Exception | None = None

    try:
        # Attempt 1: DeepSeek Responses API with strict json_schema (when enabled)
        if use_responses_api:
            for attempt in range(2):
                try:
                    raw = await _call_responses_api(
                        http=http,
                        base_url=base_url,
                        api_key=api_key,
                        model=model,
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        schema_name=schema_name,
                        json_schema=json_schema,
                    )
                    return _parse_json_model(raw, model_cls)
                except httpx.HTTPStatusError as exc:
                    last_error = exc
                    # If Responses API is unsupported (e.g. 404/400/422), fall back to chat/completions
                    if exc.response.status_code in (400, 404, 405, 422, 501):
                        logger.info(
                            "Responses API returned %s; falling back to /v1/chat/completions",
                            exc.response.status_code,
                        )
                        break
                    if attempt == 1:
                        break
                except (LLMEnrichmentError, httpx.HTTPError) as exc:
                    last_error = exc
                    logger.warning("Responses API attempt %d failed: %s", attempt + 1, exc)

        # Fallback / Generic OpenAI-compatible mode: /v1/chat/completions with json_object + 1x retry
        for attempt in range(2):
            try:
                raw = await _call_chat_completions_api(
                    http=http,
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                )
                return _parse_json_model(raw, model_cls)
            except (LLMEnrichmentError, httpx.HTTPError) as exc:
                last_error = exc
                logger.warning("Chat completions JSON attempt %d failed: %s", attempt + 1, exc)

        raise LLMEnrichmentError(f"LLM structured call failed after retries: {last_error}")
    finally:
        if close_client:
            await http.aclose()


async def classify_products_batch(
    products: list[dict[str, str | None]],
    *,
    base_url: str,
    api_key: str,
    model: str,
    use_responses_api: bool = True,
    client: httpx.AsyncClient | None = None,
) -> list[LLMProductClassification]:
    """Classify a batch of 10-15 Picnic products into macros, NOVA group, and bucket."""
    if not products:
        return []

    system_prompt = (
        "Du bist ein präziser Ernährungswissenschaftler für deutsche Supermarktprodukte (Picnic). "
        "Antworte ausschließlich als gültiges json Objekt ohne Zusatztext. "
        "Schätze für jedes Produkt realistische Nährwerte pro 100 g, die NOVA-Gruppe (1-4), "
        "ob es ein Lebensmittel ist (is_food) und den passenden bucket "
        "(produce, protein, whole_food, staple, treat_snack, beverage, household)."
    )
    example_json = json.dumps(
        {
            "products": [
                {
                    "picnic_id": "s123",
                    "is_food": True,
                    "bucket": "protein",
                    "kcal_per_100g": 63,
                    "protein_g_per_100g": 11.0,
                    "carbs_g_per_100g": 4.0,
                    "sugar_g_per_100g": 4.0,
                    "fat_g_per_100g": 0.2,
                    "fiber_g_per_100g": 0.0,
                    "nova_group": 1,
                    "confidence": 0.9,
                }
            ]
        },
        ensure_ascii=False,
    )
    user_prompt = (
        f"Klassifiziere die folgenden Produkte und gib das Ergebnis als json zurück.\n"
        f"Beispiel-Format (json): {example_json}\n\n"
        f"Produkte:\n{json.dumps(products, ensure_ascii=False)}"
    )

    result = await _structured_llm_call(
        base_url=base_url,
        api_key=api_key,
        model=model,
        use_responses_api=use_responses_api,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema_name="product_enrichment_batch",
        json_schema=PRODUCT_BATCH_JSON_SCHEMA,
        model_cls=LLMProductBatchResponse,
        client=client,
    )
    return result.products


async def score_recipe_with_llm(
    recipe_name: str,
    ingredients: list[str],
    *,
    base_url: str,
    api_key: str,
    model: str,
    use_responses_api: bool = True,
    client: httpx.AsyncClient | None = None,
) -> LLMRecipeScoreResponse:
    """Estimate a 0-100 health score and short German summary tag for a Mealie recipe."""
    system_prompt = (
        "Du bewertest Rezepte nüchtern und praxisnah nach Proteindichte, Gemüseanteil, "
        "Verarbeitungsgrad (NOVA 1-4) und Zuckergehalt. "
        "Antworte ausschließlich als gültiges json Objekt. "
        "score_summary muss ein kurzer deutscher Tag-Satz (max. 7 Wörter) sein, z. B. "
        "'Proteinreich & viel frisches Gemüse'."
    )
    example_json = json.dumps(
        {
            "health_score": 86,
            "score_summary": "Proteinreich & viel frisches Gemüse",
            "protein_level": "hoch",
            "veggie_level": "hoch",
            "nova_estimate": 1,
        },
        ensure_ascii=False,
    )
    user_prompt = (
        f"Bewerte dieses Rezept als json.\nBeispiel (json): {example_json}\n\n"
        f"Rezept: {recipe_name}\n"
        f"Zutaten: {json.dumps(ingredients[:30], ensure_ascii=False)}"
    )
    return await _structured_llm_call(
        base_url=base_url,
        api_key=api_key,
        model=model,
        use_responses_api=use_responses_api,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema_name="mealie_recipe_score",
        json_schema=RECIPE_SCORE_JSON_SCHEMA,
        model_cls=LLMRecipeScoreResponse,
        client=client,
    )


async def test_llm_connection(
    *,
    base_url: str,
    api_key: str,
    model: str,
    use_responses_api: bool = True,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Quick live sanity check against the configured LLM endpoint."""
    sample = [{"picnic_id": "test_1", "name": "Bio Brokkoli", "unit_quantity": "500 g", "category": "Obst & Gemüse"}]
    items = await classify_products_batch(
        sample,
        base_url=base_url,
        api_key=api_key,
        model=model,
        use_responses_api=use_responses_api,
        client=client,
    )
    return {
        "status": "ok",
        "model": model,
        "sample_bucket": items[0].bucket if items else None,
        "sample_nova": items[0].nova_group if items else None,
    }
