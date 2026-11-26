export type BucketType =
  | 'produce'
  | 'protein'
  | 'whole_food'
  | 'staple'
  | 'treat_snack'
  | 'beverage'
  | 'household'

export interface ScoreDriver {
  picnic_id: string
  name: string
  bucket: string
  nova_group: number | null
  reason: string
  impact: 'positive' | 'negative'
  weight_g: number
}

export interface SubScores {
  protein_score: number
  fresh_score: number
  nova_score: number
  snack_score: number
}

export interface GoalCheck {
  key: 'protein' | 'fresh' | 'nova' | 'snacks'
  label: string
  met: boolean
  detail: string
}

export interface QualityTier {
  label: string
  tone: 'sage' | 'neutral' | 'amber'
  goals_met: number
  goals_total: number
  goals: GoalCheck[]
}

export interface BasketScoreResult {
  score: number
  protein_per_1000_kcal: number
  fresh_share_pct: number
  nova_1_2_share_pct: number
  snack_share_pct: number
  total_food_weight_g: number
  included_item_count: number
  ignored_item_count: number
  sub_scores: SubScores
  tier: QualityTier
  positive_drivers: ScoreDriver[]
  negative_drivers: ScoreDriver[]
  insight_text: string
}

export interface ScoringTargets {
  protein_per_1000_kcal: number
  fresh_share_pct: number
  nova_1_2_share_pct: number
  snack_share_pct: number
}

export interface CartQuickWin {
  picnic_id: string
  name: string
  bucket: string
  unit_quantity: string | null
  score_delta: number
  projected_score: number
  reason: string
  image_url: string
}

export interface CartRemoveWin {
  picnic_id: string
  name: string
  bucket: string
  score_delta: number
  projected_score: number
  reason: string
  image_url: string
}

export interface PicnicSearchItem {
  picnic_id: string
  name: string
  unit_quantity: string | null
  price_cents: number
  image_url: string | null
  bucket: string | null
  nova_group: number | null
  in_catalog: boolean
}

export interface WeekTrendPoint {
  iso_week: string
  score: number
  protein_per_1000_kcal: number | null
  fresh_share_pct: number | null
  nova_1_2_share_pct: number | null
  snack_share_pct: number | null
}

export interface MealieRecipe {
  mealie_id: string
  slug: string
  name: string
  image_url: string | null
  health_score: number | null
  score_summary: string | null
  protein_level: string | null
  veggie_level: string | null
  nova_estimate: number | null
  scored_source: string | null
  ingredients: string[]
}

export interface MealiePlanEntry {
  id: number
  plan_date: string
  iso_week: string
  entry_type: string
  title: string
  recipe: MealieRecipe | null
}

export interface DashboardResponse {
  demo_mode: boolean
  picnic_status: string
  mealie_configured: boolean
  current_week_iso: string
  current_week_metrics: BasketScoreResult | null
  delta_vs_avg: number | null
  avg_8_weeks: number | null
  healthy_streak_weeks: number
  best_8_week_score: number | null
  is_personal_best: boolean
  pending_enrichment_count: number
  trend_8_weeks: WeekTrendPoint[]
  live_cart_score: number | null
  live_cart_item_count: number
  live_cart_total_cents: number
  top_cart_quick_win: CartQuickWin | null
  weekly_mealie_entries: MealiePlanEntry[]
  last_sync_at: string | null
}

export interface OIDCStatus {
  enabled: boolean
  authenticated: boolean
  provider_name: string
  user_email: string | null
  user_name: string | null
}

export interface DeliveryItem {
  id: number
  picnic_id: string
  display_name: string
  quantity: number
  price_cents: number
  unit_quantity: string | null
  bucket: string | null
  nova_group: number | null
  ignored: boolean
  is_food: boolean
  protein_g_per_100g: number | null
  kcal_per_100g: number | null
  image_url: string | null
}

export interface Delivery {
  delivery_id: string
  status: string
  delivery_time: string | null
  iso_week: string
  total_price_cents: number
  item_count: number
  score: number | null
  protein_per_1000_kcal: number | null
  fresh_share_pct: number | null
  nova_1_2_share_pct: number | null
  snack_share_pct: number | null
  items: DeliveryItem[]
  metrics: BasketScoreResult | null
}

export interface CartItem {
  picnic_id: string
  name: string
  quantity: number
  price_cents: number
  unit_quantity: string | null
  bucket: string
  nova_group: number | null
  ignored: boolean
  is_food: boolean
  protein_g_per_100g: number | null
  kcal_per_100g: number | null
  image_url: string | null
}

export interface RestockSuggestion {
  picnic_id: string
  name: string
  unit_quantity: string | null
  bucket: string
  image_url: string
  hits_in_recent_deliveries: number
  recent_deliveries_checked: number
}

export interface Cart {
  fetched_at: string | null
  total_price_cents: number
  item_count: number
  next_slot_start: string | null
  items: CartItem[]
  metrics: BasketScoreResult
  delta_vs_avg: number | null
  avg_8_weeks: number | null
  is_personal_best: boolean
  quick_wins: CartQuickWin[]
  remove_wins: CartRemoveWin[]
  restock_suggestions: RestockSuggestion[]
}

export interface Product {
  picnic_id: string
  name: string
  unit_quantity: string | null
  parsed_weight_g: number | null
  picnic_category: string | null
  image_id: string | null
  image_url: string | null
  gtin: string | null
  is_food: boolean
  bucket: BucketType
  kcal_per_100g: number | null
  protein_g_per_100g: number | null
  carbs_g_per_100g: number | null
  sugar_g_per_100g: number | null
  fat_g_per_100g: number | null
  fiber_g_per_100g: number | null
  nova_group: number | null
  nutriscore_grade: string | null
  enrichment_source: string
  enrichment_confidence: number | null
  enriched_at: string | null
  ignored: boolean
  ignored_reason: string | null
  manual_override: boolean
  purchase_count: number
  last_purchased_at: string | null
}

export interface SyncRun {
  id: number
  source: string
  started_at: string
  finished_at: string | null
  status: string
  summary: string | null
  error: string | null
}

export interface SettingsStatus {
  app_data_dir: string
  demo_mode: boolean
  picnic_status: string
  picnic_country_code: string
  picnic_has_token: boolean
  picnic_username_masked: string
  picnic_2fa_pending: boolean
  mealie_configured: boolean
  mealie_url: string
  mealie_token_masked: string
  llm_configured: boolean
  llm_base_url: string
  llm_model: string
  llm_use_responses_api: boolean
  llm_api_key_masked: string
  api_key_enabled: boolean
  api_key_masked: string
  sync_interval_minutes: number
  scoring_targets: ScoringTargets
  oidc_enabled: boolean
  oidc_issuer_url: string
  oidc_client_id: string
  oidc_has_secret: boolean
  oidc_allowed_emails: string
  oidc_provider_name: string
  recent_sync_runs: SyncRun[]
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  })
  if (!res.ok) {
    let message = `HTTP ${res.status}`
    try {
      const errBody = await res.json()
      if (res.status === 401 && errBody?.oidc_required && typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('sfp:oidc-required'))
      }
      if (errBody?.detail) {
        message = typeof errBody.detail === 'string' ? errBody.detail : JSON.stringify(errBody.detail)
      }
    } catch {
      // ignore non-json error body
    }
    throw new Error(message)
  }
  return res.json() as Promise<T>
}

export const api = {
  getDashboard: () => request<DashboardResponse>('/api/v1/dashboard'),
  getDeliveries: () => request<Delivery[]>('/api/v1/deliveries'),
  getCart: () => request<Cart>('/api/v1/cart'),
  refreshCart: () => request<Cart>('/api/v1/cart/refresh', { method: 'POST' }),
  addToCart: (product_id: string, count = 1) =>
    request<Cart>('/api/v1/cart/add', {
      method: 'POST',
      body: JSON.stringify({ product_id, count }),
    }),
  removeFromCart: (product_id: string, count = 1) =>
    request<Cart>('/api/v1/cart/remove', {
      method: 'POST',
      body: JSON.stringify({ product_id, count }),
    }),
  getOIDCStatus: () => request<OIDCStatus>('/api/auth/oidc/status'),
  logoutOIDC: () => request<{ status: string }>('/api/auth/oidc/logout', { method: 'POST' }),
  saveOIDCSettings: (payload: {
    enabled: boolean
    issuer_url: string
    client_id: string
    client_secret?: string
    clear_client_secret?: boolean
    allowed_emails: string
    provider_name: string
  }) =>
    request<{ status: string; message: string }>('/api/v1/settings/oidc', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  testOIDC: () =>
    request<{ status: string; issuer?: string }>('/api/v1/settings/oidc/test', {
      method: 'POST',
    }),
  getStaples: (filter: 'all' | 'high_protein' | 'fresh' | 'favorites' = 'all', q = '') =>
    request<Product[]>(
      `/api/v1/staples?filter=${encodeURIComponent(filter)}&q=${encodeURIComponent(q)}`,
    ),
  searchPicnic: (q: string) =>
    request<PicnicSearchItem[]>(`/api/v1/picnic/search?q=${encodeURIComponent(q)}`),
  getProducts: (params: { q?: string; bucket?: string; ignored?: string } = {}) => {
    const sp = new URLSearchParams()
    if (params.q) sp.set('q', params.q)
    if (params.bucket && params.bucket !== 'all') sp.set('bucket', params.bucket)
    if (params.ignored && params.ignored !== 'all') sp.set('ignored', params.ignored)
    const qs = sp.toString()
    return request<Product[]>(`/api/v1/products${qs ? `?${qs}` : ''}`)
  },
  updateProduct: (
    picnicId: string,
    patch: {
      ignored?: boolean
      ignored_reason?: string | null
      bucket?: BucketType
      nova_group?: number
      is_food?: boolean
      parsed_weight_g?: number
      kcal_per_100g?: number
      protein_g_per_100g?: number
      sugar_g_per_100g?: number
    },
  ) =>
    request<Product>(`/api/v1/products/${encodeURIComponent(picnicId)}`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    }),
  reEnrichProduct: (picnicId: string) =>
    request<Product>(`/api/v1/products/${encodeURIComponent(picnicId)}/re-enrich`, {
      method: 'POST',
    }),
  enrichProductsNow: () =>
    request<{
      status: string
      processed: number
      rule_non_food: number
      openfoodfacts: number
      llm: number
      remaining_pending: number
    }>('/api/v1/products/enrich', { method: 'POST' }),
  getMealieWeek: (isoWeek: string) =>
    request<MealiePlanEntry[]>(`/api/v1/mealie/week?iso_week=${encodeURIComponent(isoWeek)}`),
  getSettings: () => request<SettingsStatus>('/api/v1/settings'),
  saveAppSettings: (payload: {
    demo_mode?: boolean
    sync_interval_minutes?: number
    api_key?: string
    clear_api_key?: boolean
    scoring_targets?: ScoringTargets
  }) =>
    request<{ status: string; message: string }>('/api/v1/settings/app', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  clearDemoData: () =>
    request<{ status: string; message: string }>('/api/v1/settings/demo/clear', {
      method: 'POST',
    }),
  picnicLogin: (payload: { country_code: 'DE' | 'NL'; username: string; password: string }) =>
    request<{ status: string; message: string; channels?: string[] }>('/api/v1/auth/picnic/login', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  picnic2FAGenerate: (channel: 'SMS' | 'EMAIL') =>
    request<{ status: string; message: string }>('/api/v1/auth/picnic/2fa/generate', {
      method: 'POST',
      body: JSON.stringify({ channel }),
    }),
  picnic2FAVerify: (code: string) =>
    request<{ status: string; message: string }>('/api/v1/auth/picnic/2fa/verify', {
      method: 'POST',
      body: JSON.stringify({ code }),
    }),
  picnicDisconnect: () =>
    request<{ status: string; message: string }>('/api/v1/auth/picnic/disconnect', {
      method: 'POST',
    }),
  saveMealieSettings: (payload: { mealie_url: string; mealie_api_token?: string }) =>
    request<{ status: string; message: string }>('/api/v1/settings/mealie', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  testMealie: () =>
    request<{ status: string; username?: string }>('/api/v1/settings/mealie/test', {
      method: 'POST',
    }),
  saveLLMSettings: (payload: {
    llm_base_url: string
    llm_api_key?: string
    llm_model: string
    llm_use_responses_api: boolean
  }) =>
    request<{ status: string; message: string }>('/api/v1/settings/llm', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  testLLM: () =>
    request<{ status: string; model?: string; sample_bucket?: string }>('/api/v1/settings/llm/test', {
      method: 'POST',
    }),
  triggerSync: () =>
    request<{ status: string; results: Record<string, unknown> }>('/api/v1/sync', {
      method: 'POST',
    }),
}

export function formatEuro(cents: number): string {
  return (cents / 100).toLocaleString('de-DE', {
    style: 'currency',
    currency: 'EUR',
  })
}

export function formatShortDate(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString('de-DE', {
    weekday: 'short',
    day: '2-digit',
    month: '2-digit',
  })
}
