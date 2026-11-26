# Stats for Picnic

A calm, self-hosted grocery & recipe nutrition companion for **Picnic** (with optional read-only **Mealie** integration) and clean endpoints for **Tesserae** E-Ink displays & **Home Assistant**.

Built as a lightweight, zero-friction alternative to bloated calorie-tracking apps: instead of weighing every meal, **Stats for Picnic** analyzes your weekly grocery deliveries and live shopping cart using multi-person-safe quality ratios (protein density, fresh/produce share, NOVA processing level, snacks/sugar) — plus 1-click re-ordering of healthy past staples and Mealie weekly recipes with per-dish health scores.

## Key Features (v1)

- **Picnic Analytics & Pre-Checkout Check:** Sync historical deliveries + live shopping cart via `python-picnic-api2` (with in-app 2FA and persistent session tokens).
- **1-Click Re-Add from Past Purchases:** Browse past orders & healthy favorites (e.g., high-protein / fresh staples) and add items straight back into your active Picnic cart.
- **Once-Per-Product Nutrition Cache:** Enriches every new product once via **OpenFoodFacts** with a **DeepSeek Flash** (`deepseek-flash`) JSON fallback, stored permanently in SQLite.
- **Multi-Person Friendly:** Tracks ratios and trends instead of absolute calories, with 1-tap ignore flags (*Haushalt*, *Familie / Kindersnack*) per product.
- **Optional Mealie Integration (Read-Only):** Shows planned Mealie recipes with photos alongside each shopping week, complete with a cached health score per dish.
- **Tesserae & Home Assistant Ready:** Exposes a compact JSON summary (`/api/v1/summary`) and a server-rendered monochrome E-Ink widget (`/widget/eink`) with zero JS delay.
- **Single-Container Self-Hosted Stack:** 1 Docker container, 1 SQLite file (`/data/app.db`), zero push notifications, zero external databases.

## Architecture & Build Plan

See [`BUILD_PLAN.md`](./BUILD_PLAN.md) for the complete architecture, data model, API specification, DeepSeek JSON/enrichment pipeline, UI design direction, and phased implementation roadmap.
