from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import AppSetting, utcnow

# Setting keys stored in SQLite app_settings
KEY_PICNIC_AUTH_TOKEN = "picnic_auth_token"
KEY_PICNIC_COUNTRY_CODE = "picnic_country_code"
KEY_PICNIC_USERNAME = "picnic_username"
KEY_PICNIC_AUTH_STATUS = "picnic_auth_status"
KEY_PICNIC_DELIVERY_SLOTS_JSON = "picnic_delivery_slots_json"

KEY_MEALIE_URL = "mealie_url"
KEY_MEALIE_API_TOKEN = "mealie_api_token"

KEY_LLM_BASE_URL = "llm_base_url"
KEY_LLM_API_KEY = "llm_api_key"
KEY_LLM_MODEL = "llm_model"
KEY_LLM_USE_RESPONSES_API = "llm_use_responses_api"

KEY_DEMO_MODE = "app_demo_mode"
KEY_API_KEY = "app_api_key"
KEY_SYNC_INTERVAL_MINUTES = "app_sync_interval_minutes"

KEY_TARGET_PROTEIN = "target_protein_per_1000_kcal"
KEY_TARGET_FRESH = "target_fresh_share_pct"
KEY_TARGET_NOVA = "target_nova_1_2_share_pct"
KEY_TARGET_SNACKS = "target_snack_share_pct"

KEY_OIDC_ENABLED = "oidc_enabled"
KEY_OIDC_ISSUER_URL = "oidc_issuer_url"
KEY_OIDC_CLIENT_ID = "oidc_client_id"
KEY_OIDC_CLIENT_SECRET = "oidc_client_secret"
KEY_OIDC_ALLOWED_EMAILS = "oidc_allowed_emails"
KEY_OIDC_PROVIDER_NAME = "oidc_provider_name"

SECRET_KEYS = {
    KEY_PICNIC_AUTH_TOKEN,
    KEY_MEALIE_API_TOKEN,
    KEY_LLM_API_KEY,
    KEY_API_KEY,
    KEY_OIDC_CLIENT_SECRET,
}


def get_setting(db: Session, key: str, default: str = "") -> str:
    row = db.get(AppSetting, key)
    if row is None:
        return default
    if key in SECRET_KEYS:
        return get_settings().decrypt_secret(row.value)
    return row.value


def has_setting(db: Session, key: str) -> bool:
    return db.get(AppSetting, key) is not None


def set_setting(db: Session, key: str, value: str) -> None:
    stored_value = get_settings().encrypt_secret(value) if (key in SECRET_KEYS and value) else value
    row = db.get(AppSetting, key)
    if row is None:
        row = AppSetting(key=key, value=stored_value, updated_at=utcnow())
        db.add(row)
    else:
        row.value = stored_value
        row.updated_at = utcnow()
    db.commit()


def delete_setting(db: Session, key: str) -> None:
    row = db.get(AppSetting, key)
    if row is not None:
        db.delete(row)
        db.commit()


def is_demo_mode(db: Session, cfg: Settings | None = None) -> bool:
    settings = cfg or get_settings()
    raw = get_setting(db, KEY_DEMO_MODE)
    if raw == "":
        return settings.demo_mode
    return raw.lower() in ("true", "1", "yes")


def get_effective_api_key(db: Session, cfg: Settings | None = None) -> str:
    settings = cfg or get_settings()
    if has_setting(db, KEY_API_KEY):
        return get_setting(db, KEY_API_KEY).strip()
    return settings.api_key.strip()


def get_effective_sync_interval_minutes(db: Session, cfg: Settings | None = None) -> int:
    settings = cfg or get_settings()
    raw = get_setting(db, KEY_SYNC_INTERVAL_MINUTES)
    if raw == "":
        return settings.sync_interval_minutes
    try:
        return max(0, int(raw))
    except ValueError:
        return settings.sync_interval_minutes


def get_effective_mealie_config(db: Session, cfg: Settings | None = None) -> tuple[str, str]:
    settings = cfg or get_settings()
    url = get_setting(db, KEY_MEALIE_URL) or settings.mealie_url
    token = get_setting(db, KEY_MEALIE_API_TOKEN) or settings.mealie_api_token
    return url.rstrip("/"), token.strip()


def get_effective_llm_config(db: Session, cfg: Settings | None = None) -> tuple[str, str, str, bool]:
    settings = cfg or get_settings()
    base_url = (get_setting(db, KEY_LLM_BASE_URL) or settings.llm_base_url).rstrip("/")
    api_key = (get_setting(db, KEY_LLM_API_KEY) or settings.llm_api_key).strip()
    model = (get_setting(db, KEY_LLM_MODEL) or settings.llm_model).strip()
    raw_resp = get_setting(db, KEY_LLM_USE_RESPONSES_API)
    if raw_resp == "":
        use_responses = settings.llm_use_responses_api
    else:
        use_responses = raw_resp.lower() in ("true", "1", "yes")
    return base_url, api_key, model, use_responses


def _parse_float_setting(db: Session, key: str, default: float) -> float:
    raw = get_setting(db, key)
    if raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def get_effective_scoring_targets(db: Session) -> dict[str, float]:
    return {
        "protein_per_1000_kcal": _parse_float_setting(db, KEY_TARGET_PROTEIN, 35.0),
        "fresh_share_pct": _parse_float_setting(db, KEY_TARGET_FRESH, 35.0),
        "nova_1_2_share_pct": _parse_float_setting(db, KEY_TARGET_NOVA, 75.0),
        "snack_share_pct": _parse_float_setting(db, KEY_TARGET_SNACKS, 15.0),
    }


def get_effective_oidc_config(db: Session, cfg: Settings | None = None) -> dict[str, object]:
    settings = cfg or get_settings()
    enabled_raw = get_setting(db, KEY_OIDC_ENABLED, "false").lower()
    issuer = get_setting(db, KEY_OIDC_ISSUER_URL, "").strip().rstrip("/")
    client_id = get_setting(db, KEY_OIDC_CLIENT_ID, "").strip()
    client_secret = get_setting(db, KEY_OIDC_CLIENT_SECRET, "").strip()
    allowed_raw = get_setting(db, KEY_OIDC_ALLOWED_EMAILS, "").strip()
    allowed_emails = [
        e.strip().lower() for e in allowed_raw.split(",") if e.strip()
    ]
    provider_name = get_setting(db, KEY_OIDC_PROVIDER_NAME, "PocketID").strip() or "PocketID"
    enabled = (
        not settings.oidc_disable
        and enabled_raw in ("true", "1", "yes")
        and bool(issuer and client_id)
    )
    return {
        "enabled": enabled,
        "issuer_url": issuer,
        "client_id": client_id,
        "client_secret": client_secret,
        "allowed_emails": allowed_emails,
        "allowed_emails_raw": allowed_raw,
        "provider_name": provider_name,
    }


