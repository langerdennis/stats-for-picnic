# Stats for Picnic

A calm, self-hosted grocery & recipe nutrition companion for **Picnic** (with optional read-only **Mealie** integration) and clean endpoints for **Tesserae** E-Ink displays & **Home Assistant**.

Built as a lightweight, zero-friction alternative to bloated calorie-tracking apps ("Anti-SparkyFitness"): instead of weighing every meal, **Stats for Picnic** analyzes your weekly grocery deliveries and live shopping cart using multi-person-safe quality ratios (protein density, fresh/produce share, NOVA processing level, snacks/sugar) — plus 1-click re-ordering of healthy past staples and Mealie weekly recipes with per-dish health scores.

## Key Features (v1)

- **Zero-Env UI Setup:** Start the container with just a port and `/data` volume — configure Picnic 2FA, Demo Mode, Sync Interval, API Key, Mealie, and DeepSeek Flash directly in **Einstellungen** (all secrets stored encrypted in `/data/app.db`).
- **Picnic Analytics & Pre-Checkout Check:** Sync historical deliveries + live shopping cart via `python-picnic-api2` v2 with in-app 2FA and persistent encrypted session tokens.
- **1-Click Re-Add from Past Purchases:** Browse past orders & healthy favorites (*High Protein*, *Frisch*, *Favoriten*) and add items straight back into your active Picnic cart with instant Pre-Checkout score updates.
- **Once-Per-Product Nutrition Cache:** Non-food pre-filter → **OpenFoodFacts** → batched **DeepSeek Flash** (`deepseek-flash`, thinking disabled, strict JSON schema + `json_object` fallback) stored permanently in SQLite.
- **Multi-Person Friendly:** Tracks ratios and trends instead of absolute calorie budgets, with 1-tap ignore flags (*Familie*, *Haushalt*) and manual Bucket/NOVA overrides that never get overwritten.
- **Optional Mealie Integration (Read-Only):** Shows planned Mealie recipes with disk-cached proxied thumbnails alongside each shopping week, complete with a cached 0–100 health score per dish.
- **Tesserae & Home Assistant Ready:** Exposes a compact JSON summary (`GET /api/v1/summary`) and a pure server-rendered monochrome E-Ink widget (`GET /widget/eink?size=sm|md|lg&theme=mono`) with zero JS delay.
- **Single-Container Self-Hosted Stack:** 1 Docker container, 1 SQLite file (`/data/app.db`, WAL mode), zero push notifications, zero external databases.

---

## Quickstart

### 1. Docker Compose (Zero `.env` needed)

```bash
docker compose up -d
```

Open `http://localhost:8071` and open **Einstellungen** to either toggle **Demo-Modus** (8 weeks of realistic German demo data) or sign in with your real **Picnic** account (2-step 2FA), plus optionally configure **DeepSeek Flash**, **Mealie**, and a **Tesserae / Home Assistant API-Key**.

### 2. Unraid Template

An Unraid Docker template is included at [`unraid/stats-for-picnic.xml`](./unraid/stats-for-picnic.xml) (default host port `8071`, AppData path `/mnt/cache/appdata/stats-for-picnic`, image `ghcr.io/langerdennis/stats-for-picnic:latest`):

1. Copy `unraid/stats-for-picnic.xml` to `/boot/config/plugins/dockerMan/templates-user/my-stats-for-picnic.xml` on your Unraid server.
2. In the Unraid WebGUI go to **Docker → Add Container**, select `stats-for-picnic` from the template dropdown, and click **Apply**.
3. Open `http://<unraid-ip>:8071` and configure everything directly under **Einstellungen**.

---

## Tesserae & Home Assistant Integration

### Tesserae E-Ink Widget

Add a **Web** widget in Tesserae pointing to:

```text
http://<your-host>:8071/widget/eink?size=md&theme=mono
```

Supported query parameters:
- `size`: `sm` | `md` | `lg`
- `theme`: `mono` (warm e-paper `#EAE8E1` / `#141414`) | `inverted`

If you configured an **API-Key** in **Einstellungen**, pass `X-API-Key: <API_KEY>` or `Authorization: Bearer <API_KEY>` in the widget headers.

### Home Assistant REST Sensor

```yaml
rest:
  - resource: "http://<your-host>:8071/api/v1/summary"
    scan_interval: 900
    headers:
      X-API-Key: !secret stats_for_picnic_api_key
    sensor:
      - name: "Picnic Weekly Score"
        value_template: "{{ value_json.current_week.score }}"
        unit_of_measurement: "/100"
      - name: "Picnic Live Cart Score"
        value_template: "{{ value_json.live_cart.score }}"
        unit_of_measurement: "/100"
```

---

## Local Development & Tests

### Backend (Python 3.13 + `uv`)

```bash
cd backend
uv sync --dev
uv run pytest -v
uv run ruff check app tests
APP_DATA_DIR=../data uv run uvicorn app.main:app --reload --port 8080
```

### Frontend (React 19 + TypeScript + Vite + Tailwind CSS v4)

```bash
cd frontend
npm install
npm run typecheck
npm run build
npm run dev
```
