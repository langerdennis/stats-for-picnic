from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

BucketType = Literal[
    "produce",
    "protein",
    "whole_food",
    "staple",
    "treat_snack",
    "beverage",
    "household",
]

EnrichmentSourceType = Literal["pending", "rule", "openfoodfacts", "llm", "manual"]


# --- Scoring schemas ---


class ScoreDriver(BaseModel):
    picnic_id: str
    name: str
    bucket: str
    nova_group: int | None = None
    reason: str
    impact: Literal["positive", "negative"]
    weight_g: float = 0.0


class SubScores(BaseModel):
    protein_score: float = 0.0
    fresh_score: float = 0.0
    nova_score: float = 0.0
    snack_score: float = 0.0


class GoalCheck(BaseModel):
    key: Literal["protein", "fresh", "nova", "snacks"]
    label: str
    met: bool
    detail: str


class QualityTier(BaseModel):
    label: str = "Ausbaufähig"
    tone: Literal["sage", "neutral", "amber"] = "neutral"
    goals_met: int = 0
    goals_total: int = 4
    goals: list[GoalCheck] = Field(default_factory=list)


class BasketScoreResult(BaseModel):
    score: int = 0
    protein_per_1000_kcal: float = 0.0
    fresh_share_pct: float = 0.0
    nova_1_2_share_pct: float = 0.0
    snack_share_pct: float = 0.0
    total_food_weight_g: float = 0.0
    included_item_count: int = 0
    ignored_item_count: int = 0
    sub_scores: SubScores = Field(default_factory=SubScores)
    tier: QualityTier = Field(default_factory=QualityTier)
    positive_drivers: list[ScoreDriver] = Field(default_factory=list)
    negative_drivers: list[ScoreDriver] = Field(default_factory=list)
    insight_text: str = ""


class ScoringTargets(BaseModel):
    protein_per_1000_kcal: float = Field(default=35.0, ge=15.0, le=80.0)
    fresh_share_pct: float = Field(default=35.0, ge=10.0, le=70.0)
    nova_1_2_share_pct: float = Field(default=75.0, ge=40.0, le=95.0)
    snack_share_pct: float = Field(default=15.0, ge=0.0, le=40.0)


class CartQuickWin(BaseModel):
    picnic_id: str
    name: str
    bucket: str
    unit_quantity: str | None = None
    score_delta: int
    projected_score: int
    reason: str
    image_url: str


class CartRemoveWin(BaseModel):
    picnic_id: str
    name: str
    bucket: str
    score_delta: int
    projected_score: int
    reason: str
    image_url: str


class RestockSuggestion(BaseModel):
    picnic_id: str
    name: str
    unit_quantity: str | None = None
    bucket: str
    image_url: str
    hits_in_recent_deliveries: int
    recent_deliveries_checked: int


class PicnicSearchItemOut(BaseModel):
    picnic_id: str
    name: str
    unit_quantity: str | None = None
    price_cents: int = 0
    image_url: str | None = None
    bucket: str | None = None
    nova_group: int | None = None
    in_catalog: bool = False


# --- LLM structured output schemas ---


class LLMProductClassification(BaseModel):
    picnic_id: str
    is_food: bool = True
    bucket: BucketType = "staple"
    kcal_per_100g: float = Field(ge=0, le=1000)
    protein_g_per_100g: float = Field(ge=0, le=100)
    carbs_g_per_100g: float = Field(ge=0, le=100)
    sugar_g_per_100g: float = Field(ge=0, le=100)
    fat_g_per_100g: float = Field(ge=0, le=100)
    fiber_g_per_100g: float = Field(ge=0, le=100)
    nova_group: int = Field(ge=1, le=4)
    confidence: float = Field(ge=0.0, le=1.0, default=0.75)


class LLMProductBatchResponse(BaseModel):
    products: list[LLMProductClassification]


class LLMRecipeScoreResponse(BaseModel):
    health_score: int = Field(ge=0, le=100)
    score_summary: str = Field(max_length=200)
    protein_level: Literal["niedrig", "mittel", "hoch"]
    veggie_level: Literal["niedrig", "mittel", "hoch"]
    nova_estimate: int = Field(ge=1, le=4)


# --- API response & request schemas ---


class HealthResponse(BaseModel):
    status: str = "ok"
    demo_mode: bool = False
    version: str = "0.2.0"


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    picnic_id: str
    name: str
    unit_quantity: str | None = None
    parsed_weight_g: float | None = None
    picnic_category: str | None = None
    image_id: str | None = None
    image_url: str | None = None
    gtin: str | None = None
    is_food: bool
    bucket: str
    kcal_per_100g: float | None = None
    protein_g_per_100g: float | None = None
    carbs_g_per_100g: float | None = None
    sugar_g_per_100g: float | None = None
    fat_g_per_100g: float | None = None
    fiber_g_per_100g: float | None = None
    nova_group: int | None = None
    nutriscore_grade: str | None = None
    enrichment_source: str
    enrichment_confidence: float | None = None
    enriched_at: datetime | None = None
    ignored: bool
    ignored_reason: str | None = None
    manual_override: bool
    purchase_count: int
    last_purchased_at: datetime | None = None


class ProductUpdateRequest(BaseModel):
    ignored: bool | None = None
    ignored_reason: str | None = None
    bucket: BucketType | None = None
    nova_group: int | None = Field(default=None, ge=1, le=4)
    is_food: bool | None = None
    parsed_weight_g: float | None = Field(default=None, gt=0, le=50000)
    kcal_per_100g: float | None = Field(default=None, ge=0, le=1000)
    protein_g_per_100g: float | None = Field(default=None, ge=0, le=100)
    sugar_g_per_100g: float | None = Field(default=None, ge=0, le=100)


class DeliveryItemOut(BaseModel):
    id: int
    picnic_id: str
    display_name: str
    quantity: int
    price_cents: int
    unit_quantity: str | None = None
    bucket: str | None = None
    nova_group: int | None = None
    ignored: bool = False
    is_food: bool = True
    protein_g_per_100g: float | None = None
    kcal_per_100g: float | None = None
    image_url: str | None = None


class DeliveryOut(BaseModel):
    delivery_id: str
    status: str
    delivery_time: datetime | None = None
    iso_week: str
    total_price_cents: int
    item_count: int
    score: int | None = None
    protein_per_1000_kcal: float | None = None
    fresh_share_pct: float | None = None
    nova_1_2_share_pct: float | None = None
    snack_share_pct: float | None = None
    items: list[DeliveryItemOut] = Field(default_factory=list)
    metrics: BasketScoreResult | None = None


class CartItemOut(BaseModel):
    picnic_id: str
    name: str
    quantity: int
    price_cents: int
    unit_quantity: str | None = None
    bucket: str = "staple"
    nova_group: int | None = None
    ignored: bool = False
    is_food: bool = True
    protein_g_per_100g: float | None = None
    kcal_per_100g: float | None = None
    image_url: str | None = None


class CartOut(BaseModel):
    fetched_at: datetime | None = None
    total_price_cents: int = 0
    item_count: int = 0
    next_slot_start: datetime | None = None
    items: list[CartItemOut] = Field(default_factory=list)
    metrics: BasketScoreResult = Field(default_factory=BasketScoreResult)
    delta_vs_avg: int | None = None
    avg_8_weeks: float | None = None
    is_personal_best: bool = False
    quick_wins: list[CartQuickWin] = Field(default_factory=list)
    remove_wins: list[CartRemoveWin] = Field(default_factory=list)
    restock_suggestions: list[RestockSuggestion] = Field(default_factory=list)


class CartModifyRequest(BaseModel):
    product_id: str
    count: int = Field(default=1, ge=1, le=20)


class MealieRecipeOut(BaseModel):
    mealie_id: str
    slug: str
    name: str
    image_url: str | None = None
    health_score: int | None = None
    score_summary: str | None = None
    protein_level: str | None = None
    veggie_level: str | None = None
    nova_estimate: int | None = None
    scored_source: str | None = None
    ingredients: list[str] = Field(default_factory=list)


class MealiePlanEntryOut(BaseModel):
    id: int
    plan_date: date
    iso_week: str
    entry_type: str
    title: str
    recipe: MealieRecipeOut | None = None


class WeekTrendPoint(BaseModel):
    iso_week: str
    score: int
    protein_per_1000_kcal: float | None = None
    fresh_share_pct: float | None = None
    nova_1_2_share_pct: float | None = None
    snack_share_pct: float | None = None


class DashboardResponse(BaseModel):
    demo_mode: bool
    picnic_status: str
    mealie_configured: bool
    current_week_iso: str
    current_week_metrics: BasketScoreResult | None = None
    delta_vs_avg: int | None = None
    avg_8_weeks: float | None = None
    healthy_streak_weeks: int = 0
    best_8_week_score: int | None = None
    is_personal_best: bool = False
    pending_enrichment_count: int = 0
    trend_8_weeks: list[WeekTrendPoint] = Field(default_factory=list)
    live_cart_score: int | None = None
    live_cart_item_count: int = 0
    live_cart_total_cents: int = 0
    top_cart_quick_win: CartQuickWin | None = None
    weekly_mealie_entries: list[MealiePlanEntryOut] = Field(default_factory=list)
    last_sync_at: datetime | None = None


# --- Auth & Settings schemas ---


class PicnicLoginStartRequest(BaseModel):
    country_code: Literal["DE", "NL"] = "DE"
    username: str
    password: str


class Picnic2FAGenerateRequest(BaseModel):
    channel: Literal["SMS", "EMAIL"] = "SMS"


class Picnic2FAVerifyRequest(BaseModel):
    code: str = Field(min_length=4, max_length=10)


class MealieConfigRequest(BaseModel):
    mealie_url: str = ""
    mealie_api_token: str | None = None


class LLMConfigRequest(BaseModel):
    llm_base_url: str = "https://api.deepseek.com"
    llm_api_key: str | None = None
    llm_model: str = "deepseek-flash"
    llm_use_responses_api: bool = True


class OIDCConfigRequest(BaseModel):
    enabled: bool = False
    issuer_url: str = ""
    client_id: str = ""
    client_secret: str | None = None
    clear_client_secret: bool = False
    allowed_emails: str = ""
    provider_name: str = "PocketID"


class AppConfigRequest(BaseModel):
    demo_mode: bool | None = None
    sync_interval_minutes: int | None = Field(default=None, ge=0, le=1440)
    api_key: str | None = None
    clear_api_key: bool = False
    scoring_targets: ScoringTargets | None = None


class SyncRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    started_at: datetime
    finished_at: datetime | None = None
    status: str
    summary: str | None = None
    error: str | None = None


class SettingsStatusResponse(BaseModel):
    app_data_dir: str
    demo_mode: bool
    picnic_status: str
    picnic_country_code: str
    picnic_has_token: bool
    picnic_username_masked: str
    picnic_2fa_pending: bool
    mealie_configured: bool
    mealie_url: str
    mealie_token_masked: str
    llm_configured: bool
    llm_base_url: str
    llm_model: str
    llm_use_responses_api: bool
    llm_api_key_masked: str
    api_key_enabled: bool
    api_key_masked: str
    sync_interval_minutes: int
    scoring_targets: ScoringTargets = Field(default_factory=ScoringTargets)
    oidc_enabled: bool = False
    oidc_issuer_url: str = ""
    oidc_client_id: str = ""
    oidc_has_secret: bool = False
    oidc_allowed_emails: str = ""
    oidc_provider_name: str = "PocketID"
    recent_sync_runs: list[SyncRunOut] = Field(default_factory=list)


# --- Tesserae summary schema ---


class TesseraeCurrentWeek(BaseModel):
    iso_week: str
    score: int
    delta_vs_avg: int
    protein_per_1000_kcal: float
    fresh_share_pct: float
    nova_1_2_share_pct: float
    snack_share_pct: float


class TesseraeLiveCart(BaseModel):
    item_count: int
    total_cents: int
    score: int
    delta_vs_avg: int
    next_delivery_slot: str | None = None


class TesseraeTrendPoint(BaseModel):
    iso_week: str
    score: int


class TesseraeMealieToday(BaseModel):
    name: str
    health_score: int | None = None


class TesseraeSummaryResponse(BaseModel):
    updated_at: str
    picnic_status: str
    picnic_reauth_required: bool = False
    next_delivery_slot: str | None = None
    healthy_streak_weeks: int = 0
    current_week: TesseraeCurrentWeek | None = None
    live_cart: TesseraeLiveCart | None = None
    trend_8_weeks: list[TesseraeTrendPoint] = Field(default_factory=list)
    mealie_today: TesseraeMealieToday | None = None


# --- Detailed Statistics schemas ---


class StatsSummary(BaseModel):
    delivery_count: int = 0
    total_spend_cents: int = 0
    avg_spend_per_delivery_cents: int = 0
    avg_spend_per_week_cents: int = 0
    total_item_units: int = 0
    unique_products: int = 0
    total_food_weight_kg: float = 0.0
    avg_score: int | None = None
    healthy_spend_share_pct: float = 0.0
    snack_spend_share_pct: float = 0.0
    food_spend_cents: int = 0
    non_food_spend_cents: int = 0
    repeat_purchase_share_pct: float = 0.0


class BucketSpendPoint(BaseModel):
    bucket: str
    spend_cents: int
    share_pct: float
    weight_kg: float
    unit_count: int


class PeriodSpendScorePoint(BaseModel):
    period_key: str
    label: str
    spend_cents: int
    delivery_count: int
    avg_score: int | None = None


class ProductPricePoint(BaseModel):
    date: str
    unit_price_cents: int


class ProductStatItem(BaseModel):
    picnic_id: str
    name: str
    bucket: str
    unit_quantity: str | None = None
    image_url: str
    total_spend_cents: int
    total_units: int
    delivery_hits: int
    total_weight_kg: float
    avg_unit_price_cents: int
    latest_unit_price_cents: int
    price_change_pct: float | None = None
    price_history: list[ProductPricePoint] = Field(default_factory=list)


class PriceChangeItem(BaseModel):
    picnic_id: str
    name: str
    bucket: str
    image_url: str
    first_price_cents: int
    latest_price_cents: int
    delta_cents: int
    delta_pct: float
    first_date: str
    latest_date: str
    price_history: list[ProductPricePoint] = Field(default_factory=list)


class ProteinValueItem(BaseModel):
    picnic_id: str
    name: str
    bucket: str
    image_url: str
    protein_g_per_euro: float
    protein_g_per_unit: float
    avg_unit_price_cents: int
    total_units: int


class WeekdayCount(BaseModel):
    day: str
    count: int


class ShoppingHabits(BaseModel):
    avg_days_between_deliveries: float | None = None
    favorite_weekday: str | None = None
    weekday_distribution: list[WeekdayCount] = Field(default_factory=list)
    largest_delivery_cents: int = 0
    smallest_delivery_cents: int = 0
    heaviest_product_name: str | None = None
    heaviest_product_kg: float = 0.0
    most_bought_product_name: str | None = None
    most_bought_product_units: int = 0


class StatsResponse(BaseModel):
    range: Literal["30d", "90d", "1y", "all"] = "90d"
    summary: StatsSummary = Field(default_factory=StatsSummary)
    buckets: list[BucketSpendPoint] = Field(default_factory=list)
    periods: list[PeriodSpendScorePoint] = Field(default_factory=list)
    products: list[ProductStatItem] = Field(default_factory=list)
    price_changes: list[PriceChangeItem] = Field(default_factory=list)
    protein_value_leaders: list[ProteinValueItem] = Field(default_factory=list)
    habits: ShoppingHabits = Field(default_factory=ShoppingHabits)
