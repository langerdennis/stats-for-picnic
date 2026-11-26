# Stats for Picnic — Build Plan (v1)

This document captures the full product scope, technical architecture, data model, API contracts, and phased build roadmap for **Stats for Picnic** so implementation can begin cleanly in a fresh repository/session without context loss.

---

## 1. Product Vision & Scope Discipline

**Philosophy ("Anti-SparkyFitness"):**
- **Zero-friction & passive-first:** Insights emerge automatically from existing habits (weekly Picnic grocery orders + rough Mealie meal planning), without daily calorie or gram logging.
- **Completely silent:** Zero push notifications. Users check the mobile-friendly Web-UI on demand and see ambient stats on their **Tesserae** E-Ink panel in the office.
- **Multi-person household safe:** Because groceries are bought for a household (not one person), all scores are computed from **ratios and trends** (never absolute daily calorie budgets), and individual products can be flagged with 1 tap as ignored (e.g., household/non-food, family/kids snacks).
- **Tight domain boundary:** This app focuses **strictly on groceries & cooking (Picnic + optional read-only Mealie)**. Other fitness domains (Withings scale, WaterRower, Home Assistant sensors) stay outside this app — **Tesserae** composes tiles from multiple sources into the unified E-Ink dashboard.

### Explicit Non-Goals for v1
- No Withings, WaterRower, Health Connect, or Home Assistant inbound sync.
- No automatic fuzzy matching of Mealie recipe ingredients to Picnic product IDs (manual 1-click re-add of past Picnic items covers ~80% of the utility at ~10% of the complexity).
- No daily meal logging, macro diaries, or push notifications.
- No separate database/broker containers (no Postgres, no Redis, no Celery).

---

## 2. Tech Stack (1 Docker Container, 1 SQLite File)

| Layer | Technology | Rationale |
| :--- | :--- | :--- |
| **Backend** | **Python 3.13 + FastAPI + `uv`** | `python-picnic-api2` (v2.0+) provides typed Pydantic models, 2FA login, deliveries, cart, and `add_product()`. `uv` enables fast, reproducible builds. |
| **Database** | **SQLite (WAL mode) + SQLAlchemy 2.0 + Alembic** | Single file at `/data/app.db`; easy backup; zero external services. |
| **HTTP & Sync** | **`httpx` (async) + FastAPI Lifespan Background Loop** | Single async client for OpenFoodFacts, Mealie, and DeepSeek; lightweight periodic sync loop inside FastAPI. |
| **LLM Provider** | **OpenAI-compatible HTTP client (default: `deepseek-flash`)** | Configurable `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`. Default: `https://api.deepseek.com` + `deepseek-flash` (DeepSeek-V4.1-Flash). |
| **Frontend** | **React 19 + TypeScript + Vite + Tailwind CSS v4** | Built in Multi-Stage Dockerfile into `dist/` and served directly by FastAPI (no Node.js at runtime). Ideal for smooth mobile UX, live cart control, 1-click re-add, and charts. |
| **Tesserae / HA** | **`GET /api/v1/summary` (JSON) + `GET /widget/eink` (HTML/SVG)** | Pure server-rendered E-Ink tile (zero JS delay) for Tesserae's built-in `Web` widget, plus JSON API for HA REST sensors or a future native Tesserae plugin. |

### Target Repository Layout

```text
stats-for-picnic/
├── backend/
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── alembic/
│   │   └── versions/
│   ├── app/
│   │   ├── main.py                  # FastAPI app, static SPA mount, lifespan sync loop
│   │   ├── config.py                # Pydantic Settings (env + DB-backed runtime config)
│   │   ├── db.py                    # SQLite engine (WAL, foreign_keys=ON), session dep
│   │   ├── models.py                # SQLAlchemy ORM models
│   │   ├── schemas.py               # Pydantic request/response & LLM output schemas
│   │   ├── services/
│   │   │   ├── picnic_service.py    # python-picnic-api2 wrapper, 2FA state, token persistence, demo mock
│   │   │   ├── mealie_service.py    # Read-only Mealie API client, weekly plans, recipe image proxy/cache
│   │   │   ├── openfoodfacts.py     # Async OpenFoodFacts lookup (GTIN / search)
│   │   │   ├── llm_enrichment.py    # DeepSeek Flash Responses/Chat JSON client + batching
│   │   │   ├── enrichment.py        # Orchestrator: Cache → OpenFoodFacts → DeepSeek → SQLite
│   │   │   └── scoring.py           # Pure, deterministic multi-person weekly/cart & recipe scoring
│   │   └── api/
│   │       ├── auth_settings.py     # Picnic login/2FA, Mealie & LLM config endpoints
│   │       ├── picnic_routes.py     # Deliveries, cart, 1-click re-add, past staples, product overrides
│   │       ├── mealie_routes.py     # Weekly recipes, recipe image proxy, recipe re-score
│   │       └── tesserae_routes.py   # /api/v1/summary + /widget/eink
│   └── tests/
│       ├── test_scoring.py
│       ├── test_enrichment.py
│       ├── test_picnic_service.py
│       └── test_api.py
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── index.html
│   └── src/
│       ├── api/client.ts
│       ├── components/
│       └── pages/
│           ├── DashboardPage.tsx    # Weekly score, 4 ratios, 8-week trend, weekly Mealie recipes
│           ├── CartPage.tsx         # Live Picnic cart (Pre-Checkout) + 1-click re-add favorites/past items
│           ├── HistoryPage.tsx      # Past deliveries + per-week Mealie recipes & drill-down
│           ├── ProductsPage.tsx     # Cached products, bucket/NOVA tags, 1-tap ignore/override
│           └── SettingsPage.tsx     # Picnic 2FA flow, Mealie API config, DeepSeek config, Tesserae preview
├── Dockerfile                       # Multi-stage: Node (Vite build) → Python 3.13-slim + uv
├── docker-compose.yml               # 1 service, 1 /data volume, port 8080
├── .env.example
├── README.md
└── BUILD_PLAN.md
```

---

## 3. Critical Integration Details

### A) Picnic (`python-picnic-api2` v2.0+)
- **Typed Models:** v2 returns Pydantic models (`get_deliveries()`, `get_delivery(delivery_id)`, `get_cart()`, `add_product(product_id, count)`, `remove_product(product_id, count)`, `get_article(product_id, add_category=True)`). Raw payloads remain accessible via `.raw` as an escape hatch.
- **2FA & Session Persistence:**
  - Never log in repeatedly on every sync!
  - Web-UI Settings provides a guided 2-step flow:
    1. Submit country code (`DE` / `NL`), email, password → backend initiates login; if `Picnic2FARequired` is raised, allow choosing SMS/Email channel and trigger code.
    2. Submit 6-digit verification code → complete 2FA and persist the resulting `auth_token` (plus `country_code`) securely in SQLite (`app_settings`, or encrypted with an app secret key in `/data`).
  - Subsequent syncs initialize `PicnicAPI` directly with the persisted `auth_token`.
  - If a request fails with auth/401/2FA-required, mark `picnic_auth_status = "reauth_required"` (surfaces a subtle banner in the Web-UI and a status field in `/api/v1/summary`, never spams retries).
- **1-Click Re-Add:**
  - Uses `picnic.add_product(product_id, count=1)` directly from any past delivery line item or from a "Gesunde Favoriten / Häufig gekauft" list, then refreshes the live cart snapshot immediately so the Pre-Checkout score updates in real time.
- **Demo / Mock Mode (`DEMO_MODE=true`):**
  - Provide realistic seeded German grocery deliveries, live cart, and Mealie recipes so frontend, scoring, and Tesserae rendering can be developed and tested without real Picnic credentials.

### B) Two-Stage Cached Enrichment (OpenFoodFacts → DeepSeek Flash)
Every unique `picnic_product_id` is enriched **once** and permanently cached in `products`:

1. **Non-Food Pre-Filter:** Obvious Picnic non-food categories (e.g., *Haushalt*, *Drogerie*, *Pfand*, *Tierbedarf*) are auto-tagged `bucket = "household"`, `is_food = false`, `ignored = true` (`ignored_reason = "household"`) without calling external APIs.
2. **Stage 1 — OpenFoodFacts (Free, Exact Data):**
   - Query OpenFoodFacts (if GTIN/EAN is available via article metadata, fetch `/api/v2/product/{gtin}.json`; otherwise conservative name search on `de.openfoodfacts.org` with strict match validation).
   - Extract `kcal_per_100g`, `protein_g_per_100g`, `carbs_g_per_100g`, `sugar_g_per_100g`, `fat_g_per_100g`, `fiber_g_per_100g`, `nova_group` (1–4), `nutriscore_grade`, and derive `bucket` (`produce`, `protein`, `whole_food`, `staple`, `treat_snack`, `beverage`, `household`).
   - Mark `enrichment_source = "openfoodfacts"`.
3. **Stage 2 — DeepSeek Flash Fallback (Batched & Cached):**
   - Used for products where OpenFoodFacts has no confident match or lacks macros/NOVA, and for Mealie recipes without nutrition metadata.
   - **Batching:** Send 10–15 unenriched products per single LLM call (keeps initial history import fast and cheap).
   - **Exact DeepSeek API Behavior (verified against `api-docs.deepseek.com`):**
     - Model ID: `deepseek-flash` (serves DeepSeek-V4.1-Flash).
     - Base URL: `https://api.deepseek.com`.
     - **Disable thinking mode** (`"thinking": {"type": "disabled"}`) — thinking is on by default on `deepseek-flash`, and disabling it keeps structured classification fast and low-cost.
     - **Primary mode (DeepSeek Responses API `POST /v1/responses`):** Supports strict `text.format = {"type": "json_schema", "name": "product_enrichment_batch", "schema": ...}`.
     - **Fallback / Generic OpenAI-compatible mode (`POST /v1/chat/completions`):** Uses `response_format = {"type": "json_object"}` (for non-DeepSeek endpoints like Ollama/OpenRouter or if Responses API fails). Must include the word `"json"` + a concise example in the prompt, check for empty/whitespace-only content (DeepSeek replaces unparseable non-JSON with spaces in `json_object` mode), validate via Pydantic, and perform 1× automatic retry on parse/validation failure.
   - Mark `enrichment_source = "llm"`, store `enrichment_confidence` and `enriched_at`.
4. **Manual Override (Always Wins):**
   - Users can toggle `ignored` (e.g., *Ignoriert (Familie)* / *Haushalt*) or override `bucket` / `nova_group` in the Web-UI. Manual edits set `manual_override = true` so re-syncs never overwrite user choices.

### C) Optional Read-Only Mealie Integration
- Configured via `MEALIE_URL` + `MEALIE_API_TOKEN` (optional — app works 100% cleanly without Mealie).
- **Weekly Recipe Association:** Fetch Mealie meal plans (`GET /api/households/mealplans?start_date=...&end_date=...`) and align them with each ISO week / Picnic delivery week.
- **Recipe Images:** Backend proxies and disk-caches Mealie recipe thumbnails (`GET /api/v1/mealie/recipes/{mealie_id}/image` → upstream `{MEALIE_URL}/api/media/recipes/{mealie_id}/images/min-original.webp`) so the browser never needs Mealie tokens or mixed-content access.
- **Health Score per Recipe (0–100):**
  - If Mealie `recipe.nutrition` has usable values, compute directly via `scoring.py`.
  - Otherwise, send recipe name + ingredient list once to `deepseek-flash` (structured JSON: estimated protein/kcal/fiber/sugar balance, vegetable share, processing level 1–4, 1-sentence German summary tag like *"Proteinreich & viel Gemüse"*).
  - Cached in `mealie_recipes` keyed by `mealie_id` + `mealie_updated_at` (only re-evaluated when the recipe is actually edited in Mealie).

### D) Multi-Person Scoring Engine (`services/scoring.py`)
Must be **pure, deterministic, transparent, and thoroughly unit-tested**:
- Filter items: include only `is_food == true` and `ignored == false`.
- Weight each line item by estimated edible weight (`unit_weight_g * quantity`, fallback sensible default by category/unit string like `"500 g"`, `"1 kg"`, `"6 Stück"` parsed via helper) — or price-weighted fallback if weight is unknown, clearly documented.
- Compute 4 core household-independent ratios:
  1. **Protein Density (`protein_per_1000_kcal`):** Total protein (g) / (Total kcal / 1000). Target benchmark ~35–45 g / 1.000 kcal.
  2. **Fresh & Produce Share (`fresh_share_pct`):** Share of food items in `produce` (fruits, vegetables, herbs, legumes). Target benchmark ≥ 35–45 %.
  3. **Unprocessed Share (`nova_1_2_share_pct`):** Share of food items with `nova_group in (1, 2)`. Target benchmark ≥ 75 %.
  4. **Snacks & Sugar Share (`snack_sugar_share_pct`):** Share of food items in `treat_snack` / sugary beverages or high sugar density. Lower is better (target ≤ 15 %).
- Combine into a single **Weekly / Cart Score (0–100)** with transparent, inspectable sub-scores (e.g., 30% Protein Density + 25% Fresh/Produce + 25% NOVA 1–2 + 20% Low Snack/Sugar), plus delta vs. 8-week rolling average (`+6 vs. Schnitt`).
- Also compute **Top Positive Drivers** and **Top Negative Drivers** per delivery/cart so the UI can explain *why* the cart is at Score 81.

### E) Tesserae & Home Assistant Outputs
1. **`GET /api/v1/summary`** (optional `Authorization: Bearer <API_KEY>` or `X-API-Key` header if `API_KEY` is configured):
   ```json
   {
     "updated_at": "2026-11-26T08:15:00Z",
     "picnic_status": "ok",
     "current_week": {
       "iso_week": "2026-W48",
       "score": 78,
       "delta_vs_avg": 6,
       "protein_per_1000_kcal": 38.4,
       "fresh_share_pct": 44.0,
       "nova_1_2_share_pct": 76.0,
       "snack_share_pct": 14.0
     },
     "live_cart": {
       "item_count": 24,
       "total_cents": 6840,
       "score": 81,
       "delta_vs_avg": 9,
       "next_delivery_slot": "2026-11-28T17:00:00+01:00"
     },
     "trend_8_weeks": [
       {"iso_week": "2026-W41", "score": 64},
       {"iso_week": "2026-W48", "score": 78}
     ],
     "mealie_today": {
       "name": "Lachs-Bowl mit Brokkoli",
       "health_score": 88
     }
   }
   ```
2. **`GET /widget/eink`** (query params e.g. `?size=sm|md|lg&theme=mono`):
   - Server-rendered pure HTML + inline SVG (no external fonts, no JS fetch wait, no `X-Frame-Options: DENY`).
   - Monochrome Braun/Dieter-Rams e-paper aesthetic (`#EAE8E1` paper background, `#141414` deep black ink, crisp 1px hairlines, tabular numbers): displays Picnic Weekly Score + progress bar, 4 compact ratios or Pre-Checkout cart badge, mini 8-week SVG sparkline, and optional today's Mealie recipe line.
   - Ready to drop straight into Tesserae's built-in **Web** widget (with header auth if `API_KEY` is set).

---

## 4. Data Model (SQLite Tables)

- **`app_settings`**: key-value store (`key TEXT PRIMARY KEY`, `value TEXT`, `updated_at`) for persisted Picnic token/country, Mealie URL/token, LLM config, sync timestamps, and scoring targets.
- **`products`**:
  - `picnic_id TEXT PRIMARY KEY`, `name TEXT`, `unit_quantity TEXT`, `parsed_weight_g REAL`, `picnic_category TEXT`, `image_id TEXT`, `gtin TEXT`
  - `is_food BOOLEAN`, `bucket TEXT` (`produce` | `protein` | `whole_food` | `staple` | `treat_snack` | `beverage` | `household`)
  - `kcal_per_100g REAL`, `protein_g_per_100g REAL`, `carbs_g_per_100g REAL`, `sugar_g_per_100g REAL`, `fat_g_per_100g REAL`, `fiber_g_per_100g REAL`, `nova_group INTEGER`
  - `enrichment_source TEXT` (`pending` | `rule` | `openfoodfacts` | `llm` | `manual`), `enrichment_confidence REAL`, `enriched_at DATETIME`
  - `ignored BOOLEAN DEFAULT FALSE`, `ignored_reason TEXT`, `manual_override BOOLEAN DEFAULT FALSE`
  - `purchase_count INTEGER DEFAULT 0`, `last_purchased_at DATETIME`
- **`deliveries`**:
  - `delivery_id TEXT PRIMARY KEY`, `status TEXT`, `delivery_time DATETIME`, `iso_week TEXT`, `total_price_cents INTEGER`, `item_count INTEGER`
  - Cached computed metrics (`score REAL`, `protein_per_1000_kcal REAL`, `fresh_share_pct REAL`, `nova_1_2_share_pct REAL`, `snack_share_pct REAL`), `raw_json TEXT`
- **`delivery_items`**:
  - `id INTEGER PRIMARY KEY`, `delivery_id TEXT FK`, `picnic_id TEXT FK`, `quantity INTEGER`, `price_cents INTEGER`, `display_name TEXT`
- **`cart_snapshots`** (latest live cart):
  - `id INTEGER PRIMARY KEY`, `fetched_at DATETIME`, `total_price_cents INTEGER`, `item_count INTEGER`, `next_slot_start DATETIME`, `items_json TEXT`, `computed_metrics_json TEXT`
- **`mealie_recipes`**:
  - `mealie_id TEXT PRIMARY KEY`, `slug TEXT`, `name TEXT`, `mealie_updated_at TEXT`, `image_cached_path TEXT`
  - `ingredients_json TEXT`, `nutrition_json TEXT`
  - `health_score INTEGER`, `score_summary TEXT`, `protein_level TEXT`, `veggie_level TEXT`, `nova_estimate INTEGER`, `scored_source TEXT`, `scored_at DATETIME`
- **`mealie_mealplans`**:
  - `id INTEGER PRIMARY KEY`, `plan_date DATE`, `iso_week TEXT`, `entry_type TEXT` (`breakfast` | `lunch` | `dinner` | `side`), `mealie_recipe_id TEXT FK`, `title TEXT`
- **`sync_runs`**:
  - `id INTEGER PRIMARY KEY`, `source TEXT` (`picnic` | `mealie` | `enrichment`), `started_at DATETIME`, `finished_at DATETIME`, `status TEXT`, `summary TEXT`, `error TEXT`

---

## 5. Visual Design Direction

- **Web-UI (Mobile-First Responsive, German UI Copy):**
  - Warm paper background (`#F8F7F4`), crisp white cards (`#FFFFFF`) with subtle `1px` borders (`#E5E4DF`), deep charcoal text (`#18181B`), muted sage green (`#2E7D5B`) for positive health metrics, soft amber (`#D97706`) for snacks/watch items.
  - Calm Apple-Health-meets-Linear aesthetic — generous whitespace, zero neon/gamification clutter.
  - Navigation tabs: **Übersicht**, **Warenkorb**, **Einkäufe**, **Produkte**, **Einstellungen** (bottom nav on mobile, clean top pill bar on desktop).
  - Mealie weekly recipes render as clean visual cards with recipe thumbnail + compact health score pill (`88/100`) right next to the weekly grocery breakdown.
- **Tesserae E-Ink Widget (`/widget/eink`):**
  - Authentic flat monochrome e-paper palette (`#EAE8E1`, `#141414`, `#666666`, `#C2C0B8`), sharp 1px black hairlines, bold tabular numbers, zero gradients/shadows.

---

## 6. Phased Implementation Roadmap

### Phase 1: Foundation & Docker Scaffold
- Initialize `backend/` with `uv` (`pyproject.toml`), FastAPI, SQLAlchemy 2.0, Alembic, SQLite WAL setup, and `app/config.py`.
- Initialize `frontend/` with Vite + React 19 + TypeScript + Tailwind CSS v4.
- Create multi-stage `Dockerfile`, `docker-compose.yml`, and `.env.example`.
- **Done when:** `pytest` passes healthcheck test, `npm run build` succeeds, and `docker build` produces a working single-container image serving both API and built frontend.

### Phase 2: Picnic Integration, 2FA Flow & Demo Mode
- Implement `picnic_service.py` wrapping `python-picnic-api2` v2:
  - 2-step 2FA login flow + persistent `auth_token` in SQLite.
  - Historical deliveries sync (`get_deliveries` + `get_delivery`), live cart fetch (`get_cart`), and 1-click re-add (`add_product` / `remove_product`).
  - Realistic `DEMO_MODE=true` provider so everything works out-of-the-box without real credentials.
- **Done when:** Demo mode syncs mock deliveries & live cart into SQLite; real Picnic 2FA endpoints are wired and unit-tested with mocked `python-picnic-api2` responses.

### Phase 3: Enrichment Pipeline & Scoring Engine
- Implement `openfoodfacts.py`, `llm_enrichment.py` (DeepSeek Flash Responses API `json_schema` + Chat Completions `json_object` fallback + `"thinking": {"type": "disabled"}` + batching + Pydantic validation/retry), and `enrichment.py`.
- Implement pure `scoring.py` (weight parser, 4 household-safe ratios, 0–100 score, 8-week trend, top positive/negative drivers).
- **Done when:** Comprehensive `pytest` coverage on `scoring.py` and `enrichment.py` (including non-food skip, OpenFoodFacts hit, DeepSeek batch fallback, blank-JSON retry, and manual override preservation).

### Phase 4: Mealie Read-Only Integration
- Implement `mealie_service.py`: weekly meal plan sync, recipe image proxy/cache, and per-recipe Health Score (Mealie nutrition first → DeepSeek Flash cached fallback).
- **Done when:** Weekly endpoints include planned Mealie recipes with cached thumbnails and health scores (and degrade gracefully when Mealie is not configured).

### Phase 5: Mobile-First Web-UI
- Build all 5 views matching the calm warm-paper design:
  - **Übersicht:** Current week score + 4 ratio bars + 8-week trend chart + planned Mealie recipes with photos & health scores.
  - **Warenkorb (Pre-Checkout):** Live Picnic cart score + insight banner + cart items + **"Aus vergangenen Einkäufen hinzufügen"** drawer/panel with quick filters (*High Protein*, *Frisch*, *Favoriten*) and 1-click `+1` button.
  - **Einkäufe:** Historical deliveries list with per-delivery score breakdown and associated Mealie week.
  - **Produkte:** Searchable cached product catalog with 1-tap *Ignorieren (Familie / Haushalt)* and bucket/NOVA override.
  - **Einstellungen:** Picnic 2FA setup & connection status, Mealie config, DeepSeek API config + test button, sync trigger, and Tesserae URL/preview helper.
- **Done when:** Full end-to-end flow works smoothly on mobile and desktop viewports in `DEMO_MODE=true` and passes frontend typecheck + production build.

### Phase 6: Tesserae Endpoints, Hardening & Pre-Public Polish
- Build `GET /api/v1/summary` and `GET /widget/eink` (monochrome server-rendered HTML/SVG, verified at `sm`/`md`/`lg` cell sizes).
- Security review: API key protection on Tesserae/external endpoints, secrets masked in settings responses and never logged, safe error handling if Picnic 2FA expires.
- Add real-world testing instructions and polish `README.md` with screenshots.

---

## 7. Environment Variables (`.env.example` Contract)

```env
# App
APP_DATA_DIR=/data
DEMO_MODE=false
API_KEY=                          # Optional: protects /api/v1/summary & /widget/eink
SYNC_INTERVAL_MINUTES=60

# LLM (OpenAI-compatible; default DeepSeek Flash)
LLM_BASE_URL=https://api.deepseek.com
LLM_API_KEY=
LLM_MODEL=deepseek-flash
LLM_USE_RESPONSES_API=true        # Uses strict json_schema on DeepSeek; set false for generic chat/completions

# Mealie (Optional, read-only; can also be configured in Web-UI)
MEALIE_URL=
MEALIE_API_TOKEN=
```

*(Picnic credentials & 2FA token are configured interactively in the Web-UI Settings page and persisted in `/data/app.db` rather than hardcoded in `.env`.)*

---

## 8. Pre-Public Checklist (Before Switching Repo from Private to Public)

- [ ] Real-world smoke test with live Picnic account (2FA flow, token survival across container restart, 1-click re-add).
- [ ] Real-world smoke test with Mealie instance (images, weekly plan, recipe health scores).
- [ ] Real-world test of `GET /widget/eink` inside Tesserae Web widget on the actual E-Ink panel.
- [ ] Verify no personal tokens, receipts, or SQLite files ever entered git history (`git log --stat`).
- [ ] Update `README.md` with Docker Compose quickstart, screenshots, and license (e.g., MIT).
