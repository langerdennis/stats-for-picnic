from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.config import get_settings, mask_secret
from app.db import get_db
from app.models import SyncRun
from app.schemas import (
    AppConfigRequest,
    LLMConfigRequest,
    MealieConfigRequest,
    Picnic2FAGenerateRequest,
    Picnic2FAVerifyRequest,
    PicnicLoginStartRequest,
    SettingsStatusResponse,
    SyncRunOut,
)
from app.services.enrichment import enrich_pending_products
from app.services.llm_enrichment import LLMEnrichmentError, test_llm_connection
from app.services.mealie_service import (
    MealieServiceError,
    is_mealie_configured,
    seed_demo_mealie_data,
    sync_mealie,
    test_mealie_connection,
)
from app.services.picnic_service import (
    PicnicReauthRequiredError,
    PicnicServiceError,
    clear_demo_data,
    disconnect_picnic,
    get_picnic_status,
    has_pending_2fa,
    request_2fa_code,
    seed_demo_picnic_data,
    start_login,
    sync_picnic,
    verify_2fa_code,
)
from app.services.settings_store import (
    KEY_API_KEY,
    KEY_DEMO_MODE,
    KEY_LLM_API_KEY,
    KEY_LLM_BASE_URL,
    KEY_LLM_MODEL,
    KEY_LLM_USE_RESPONSES_API,
    KEY_MEALIE_API_TOKEN,
    KEY_MEALIE_URL,
    KEY_PICNIC_AUTH_TOKEN,
    KEY_PICNIC_COUNTRY_CODE,
    KEY_PICNIC_USERNAME,
    KEY_SYNC_INTERVAL_MINUTES,
    get_effective_api_key,
    get_effective_llm_config,
    get_effective_mealie_config,
    get_effective_sync_interval_minutes,
    get_setting,
    is_demo_mode,
    set_setting,
)

router = APIRouter(prefix="/api/v1", tags=["settings-auth"])


@router.get("/settings", response_model=SettingsStatusResponse)
def get_settings_status(db: Session = Depends(get_db)) -> SettingsStatusResponse:
    cfg = get_settings()
    picnic_token = get_setting(db, KEY_PICNIC_AUTH_TOKEN)
    picnic_username = get_setting(db, KEY_PICNIC_USERNAME)
    picnic_country = get_setting(db, KEY_PICNIC_COUNTRY_CODE, "DE") or "DE"

    mealie_url, mealie_token = get_effective_mealie_config(db, cfg)
    llm_base, llm_key, llm_model, llm_responses = get_effective_llm_config(db, cfg)
    effective_api_key = get_effective_api_key(db, cfg)

    recent_runs = list(db.scalars(select(SyncRun).order_by(desc(SyncRun.id)).limit(8)))

    return SettingsStatusResponse(
        app_data_dir=cfg.app_data_dir,
        demo_mode=is_demo_mode(db, cfg),
        picnic_status=get_picnic_status(db),
        picnic_country_code=picnic_country,
        picnic_has_token=bool(picnic_token),
        picnic_username_masked=mask_secret(picnic_username),
        picnic_2fa_pending=has_pending_2fa(),
        mealie_configured=is_mealie_configured(db),
        mealie_url=mealie_url,
        mealie_token_masked=mask_secret(mealie_token),
        llm_configured=bool(llm_key),
        llm_base_url=llm_base,
        llm_model=llm_model,
        llm_use_responses_api=llm_responses,
        llm_api_key_masked=mask_secret(llm_key),
        api_key_enabled=bool(effective_api_key),
        api_key_masked=mask_secret(effective_api_key),
        sync_interval_minutes=get_effective_sync_interval_minutes(db, cfg),
        recent_sync_runs=[SyncRunOut.model_validate(r) for r in recent_runs],
    )


@router.put("/settings/app")
def update_app_settings(
    body: AppConfigRequest,
    db: Session = Depends(get_db),
) -> dict:
    if body.demo_mode is not None:
        set_setting(db, KEY_DEMO_MODE, "true" if body.demo_mode else "false")
        if body.demo_mode:
            seed_demo_picnic_data(db)
            seed_demo_mealie_data(db)

    if body.sync_interval_minutes is not None:
        set_setting(db, KEY_SYNC_INTERVAL_MINUTES, str(body.sync_interval_minutes))

    if body.clear_api_key:
        set_setting(db, KEY_API_KEY, "")
    elif body.api_key is not None and body.api_key.strip() != "":
        set_setting(db, KEY_API_KEY, body.api_key.strip())

    return {"status": "ok", "message": "App-Einstellungen gespeichert."}


@router.post("/settings/demo/clear")
def clear_demo_dataset(db: Session = Depends(get_db)) -> dict:
    removed = clear_demo_data(db)
    return {
        "status": "ok",
        "message": (
            f"Demo-Daten bereinigt ({removed['deliveries_removed']} Lieferungen, "
            f"{removed['products_removed']} Produkte, {removed['recipes_removed']} Rezepte entfernt)."
        ),
        **removed,
    }


@router.post("/auth/picnic/login")
async def picnic_login_start(
    body: PicnicLoginStartRequest,
    db: Session = Depends(get_db),
) -> dict:
    try:
        res = start_login(
            db=db,
            country_code=body.country_code,
            username=body.username.strip(),
            password=body.password,
        )
    except PicnicServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if res.get("status") == "ok":
        try:
            sync_picnic(db)
            await enrich_pending_products(db)
            res["initial_sync"] = "ok"
            res["message"] = "Mit Picnic verbunden und erste Einkäufe geladen."
        except Exception:
            res["initial_sync"] = "deferred"
    return res


@router.post("/auth/picnic/2fa/generate")
def picnic_2fa_generate(
    body: Picnic2FAGenerateRequest,
    db: Session = Depends(get_db),
) -> dict:
    try:
        return request_2fa_code(db=db, channel=body.channel)
    except PicnicServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/auth/picnic/2fa/verify")
async def picnic_2fa_verify(
    body: Picnic2FAVerifyRequest,
    db: Session = Depends(get_db),
) -> dict:
    try:
        res = verify_2fa_code(db=db, code=body.code)
    except PicnicServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        sync_picnic(db)
        await enrich_pending_products(db)
        res["initial_sync"] = "ok"
        res["message"] = "Picnic 2FA abgeschlossen und erste Einkäufe synchronisiert."
    except Exception:
        res["initial_sync"] = "deferred"
    return res


@router.post("/auth/picnic/disconnect")
def picnic_disconnect(db: Session = Depends(get_db)) -> dict:
    disconnect_picnic(db)
    return {"status": "not_configured", "message": "Picnic-Verbindung getrennt."}


@router.put("/settings/mealie")
def update_mealie_settings(
    body: MealieConfigRequest,
    db: Session = Depends(get_db),
) -> dict:
    set_setting(db, KEY_MEALIE_URL, body.mealie_url.strip().rstrip("/"))
    if body.mealie_api_token is not None and body.mealie_api_token.strip() != "":
        set_setting(db, KEY_MEALIE_API_TOKEN, body.mealie_api_token.strip())
    return {"status": "ok", "message": "Mealie-Einstellungen gespeichert."}


@router.post("/settings/mealie/test")
async def test_mealie_settings(db: Session = Depends(get_db)) -> dict:
    url, token = get_effective_mealie_config(db)
    try:
        return await test_mealie_connection(url, token)
    except MealieServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/settings/llm")
def update_llm_settings(
    body: LLMConfigRequest,
    db: Session = Depends(get_db),
) -> dict:
    set_setting(db, KEY_LLM_BASE_URL, body.llm_base_url.strip().rstrip("/"))
    set_setting(db, KEY_LLM_MODEL, body.llm_model.strip() or "deepseek-flash")
    set_setting(db, KEY_LLM_USE_RESPONSES_API, "true" if body.llm_use_responses_api else "false")
    if body.llm_api_key is not None and body.llm_api_key.strip() != "":
        set_setting(db, KEY_LLM_API_KEY, body.llm_api_key.strip())
    return {"status": "ok", "message": "LLM-Einstellungen gespeichert."}


@router.post("/settings/llm/test")
async def test_llm_settings(db: Session = Depends(get_db)) -> dict:
    base_url, api_key, model, use_responses = get_effective_llm_config(db)
    if not api_key:
        raise HTTPException(status_code=400, detail="Kein LLM API-Key konfiguriert.")
    try:
        return await test_llm_connection(
            base_url=base_url,
            api_key=api_key,
            model=model,
            use_responses_api=use_responses,
        )
    except LLMEnrichmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/sync")
async def trigger_manual_sync(db: Session = Depends(get_db)) -> dict:
    results: dict[str, object] = {}
    try:
        results["picnic"] = sync_picnic(db)
    except PicnicReauthRequiredError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except PicnicServiceError as exc:
        results["picnic"] = {"status": "error", "detail": str(exc)}

    results["enrichment"] = await enrich_pending_products(db)

    try:
        results["mealie"] = await sync_mealie(db)
    except MealieServiceError as exc:
        results["mealie"] = {"status": "error", "detail": str(exc)}

    return {"status": "ok", "results": results}
