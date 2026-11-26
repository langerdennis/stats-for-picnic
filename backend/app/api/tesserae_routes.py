from __future__ import annotations

import html
import json
import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.picnic_routes import build_weekly_trend
from app.db import get_db
from app.models import CartSnapshot, MealieMealplan, MealieRecipe, Product
from app.schemas import (
    TesseraeCurrentWeek,
    TesseraeLiveCart,
    TesseraeMealieToday,
    TesseraeSummaryResponse,
    TesseraeTrendPoint,
)
from app.services.picnic_service import get_picnic_status, product_to_scorable
from app.services.scoring import (
    compute_healthy_streak,
    compute_rolling_average_and_delta,
    score_basket,
)
from app.services.settings_store import get_effective_scoring_targets

router = APIRouter(tags=["tesserae"])


def verify_optional_api_key(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
) -> None:
    from app.services.settings_store import get_effective_api_key

    expected = get_effective_api_key(db)
    if not expected:
        return
    provided = ""
    if x_api_key:
        provided = x_api_key.strip()
    elif authorization and authorization.lower().startswith("bearer "):
        provided = authorization[7:].strip()

    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=401,
            detail="Ungültiger oder fehlender API-Key (Authorization: Bearer oder X-API-Key).",
        )


def _collect_summary(db: Session) -> TesseraeSummaryResponse:
    from app.schemas import ScoringTargets

    now = datetime.now(UTC)
    targets = ScoringTargets(**get_effective_scoring_targets(db))
    trend, week_metrics = build_weekly_trend(db)
    hist_scores = [pt.score for pt in trend]
    baseline_scores = hist_scores[:-1] if len(hist_scores) >= 2 else hist_scores
    streak = compute_healthy_streak(hist_scores, threshold=75)

    current_week_obj: TesseraeCurrentWeek | None = None
    if trend:
        latest_wk = trend[-1].iso_week
        wm = week_metrics[latest_wk]
        _, delta = compute_rolling_average_and_delta(wm.score, baseline_scores)
        current_week_obj = TesseraeCurrentWeek(
            iso_week=latest_wk,
            score=wm.score,
            delta_vs_avg=delta or 0,
            protein_per_1000_kcal=wm.protein_per_1000_kcal,
            fresh_share_pct=wm.fresh_share_pct,
            nova_1_2_share_pct=wm.nova_1_2_share_pct,
            snack_share_pct=wm.snack_share_pct,
        )

    live_cart_obj: TesseraeLiveCart | None = None
    snap = db.scalar(select(CartSnapshot).order_by(desc(CartSnapshot.id)).limit(1))
    if snap is not None and snap.item_count > 0:
        raw_items = json.loads(snap.items_json or "[]")
        scorable = []
        for entry in raw_items:
            prod = db.get(Product, entry["picnic_id"])
            if prod is not None:
                scorable.append(
                    product_to_scorable(
                        prod,
                        int(entry.get("quantity", 1)),
                        int(entry.get("price_cents", 0)),
                    )
                )
        cart_metrics = score_basket(scorable, targets=targets)
        _, cart_delta = compute_rolling_average_and_delta(cart_metrics.score, hist_scores)
        live_cart_obj = TesseraeLiveCart(
            item_count=snap.item_count,
            total_cents=snap.total_price_cents,
            score=cart_metrics.score,
            delta_vs_avg=cart_delta or 0,
            next_delivery_slot=snap.next_slot_start.isoformat() if snap.next_slot_start else None,
        )

    mealie_today_obj: TesseraeMealieToday | None = None
    today = now.date()
    todays_plan = db.scalar(
        select(MealieMealplan)
        .where(MealieMealplan.plan_date == today)
        .order_by(MealieMealplan.id.asc())
        .limit(1)
    )
    if todays_plan is not None:
        rec = (
            db.get(MealieRecipe, todays_plan.mealie_recipe_id)
            if todays_plan.mealie_recipe_id
            else None
        )
        mealie_today_obj = TesseraeMealieToday(
            name=rec.name if rec else todays_plan.title,
            health_score=rec.health_score if rec else None,
        )

    picnic_status = get_picnic_status(db)
    next_slot_iso = (
        snap.next_slot_start.isoformat()
        if snap is not None and snap.next_slot_start is not None
        else None
    )

    return TesseraeSummaryResponse(
        updated_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        picnic_status=picnic_status,
        picnic_reauth_required=picnic_status == "reauth_required",
        next_delivery_slot=next_slot_iso,
        healthy_streak_weeks=streak,
        current_week=current_week_obj,
        live_cart=live_cart_obj,
        trend_8_weeks=[TesseraeTrendPoint(iso_week=p.iso_week, score=p.score) for p in trend],
        mealie_today=mealie_today_obj,
    )


def _format_eink_slot(iso_slot: str | None) -> str:
    if not iso_slot:
        return ""
    try:
        dt = datetime.fromisoformat(iso_slot.replace("Z", "+00:00"))
        days = ["MO", "DI", "MI", "DO", "FR", "SA", "SO"]
        return f" · {days[dt.weekday()]} {dt.strftime('%H:%M')}"
    except ValueError:
        return ""


@router.get(
    "/api/v1/summary",
    response_model=TesseraeSummaryResponse,
    dependencies=[Depends(verify_optional_api_key)],
)
def get_tesserae_summary(db: Session = Depends(get_db)) -> TesseraeSummaryResponse:
    return _collect_summary(db)


def _render_sparkline_svg(points: list[TesseraeTrendPoint], width: int = 180, height: int = 38) -> str:
    if len(points) < 2:
        return (
            f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
            f'xmlns="http://www.w3.org/2000/svg">'
            f'<line x1="2" y1="{height // 2}" x2="{width - 2}" y2="{height // 2}" '
            f'stroke="#C2C0B8" stroke-width="1.5" stroke-dasharray="3 3"/></svg>'
        )
    scores = [p.score for p in points]
    min_s = min(min(scores), 45)
    max_s = max(max(scores), 95)
    span = max(10, max_s - min_s)
    pad_x = 5
    pad_y = 6
    step_x = (width - 2 * pad_x) / (len(scores) - 1)

    coords: list[tuple[float, float]] = []
    for idx, s in enumerate(scores):
        x = pad_x + idx * step_x
        y = height - pad_y - ((s - min_s) / span) * (height - 2 * pad_y)
        coords.append((round(x, 1), round(y, 1)))

    poly = " ".join(f"{x},{y}" for x, y in coords)
    lx, ly = coords[-1]
    baseline_y = height - pad_y
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="8-Wochen-Trend">'
        f'<line x1="{pad_x}" y1="{baseline_y}" x2="{width - pad_x}" y2="{baseline_y}" '
        f'stroke="#C2C0B8" stroke-width="1"/>'
        f'<polyline fill="none" stroke="#141414" stroke-width="2" '
        f'stroke-linejoin="miter" stroke-linecap="square" points="{poly}"/>'
        f'<circle cx="{lx}" cy="{ly}" r="3.2" fill="#141414"/>'
        f"</svg>"
    )


@router.get(
    "/widget/eink",
    response_class=HTMLResponse,
    dependencies=[Depends(verify_optional_api_key)],
)
def get_eink_widget(
    size: str = Query(default="md", pattern="^(sm|md|lg)$"),
    theme: str = Query(default="mono", pattern="^(mono|inverted)$"),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    summary = _collect_summary(db)

    if theme == "inverted":
        bg, ink, muted, rule = "#141414", "#EAE8E1", "#A8A69E", "#3F3E3A"
    else:
        bg, ink, muted, rule = "#EAE8E1", "#141414", "#666666", "#C2C0B8"

    cw = summary.current_week
    score_val = cw.score if cw else 0
    delta_val = cw.delta_vs_avg if cw else 0
    delta_str = f"{'+' if delta_val >= 0 else ''}{delta_val} vs. Schnitt"
    week_label = cw.iso_week if cw else "—"

    badges: list[str] = []
    if summary.healthy_streak_weeks >= 2:
        badges.append(f'<span class="badge">SERIE {summary.healthy_streak_weeks}W</span>')
    if summary.picnic_status == "reauth_required":
        badges.append('<span class="badge">2FA ERNEUERN</span>')
    elif summary.picnic_status == "demo":
        badges.append('<span class="badge">DEMO</span>')
    status_badge = " ".join(badges)

    cart = summary.live_cart
    cart_html = ""
    if cart is not None:
        euros = f"{cart.total_cents / 100:.2f}".replace(".", ",")
        cart_delta = f"{'+' if cart.delta_vs_avg >= 0 else ''}{cart.delta_vs_avg}"
        slot_suffix = _format_eink_slot(cart.next_delivery_slot) if size == "lg" else ""
        cart_html = (
            f'<div class="cart-strip">'
            f'<span class="k">WARENKORB ({cart.item_count}){html.escape(slot_suffix)}</span>'
            f'<span class="v">SCORE {cart.score} ({cart_delta}) · {euros} €</span>'
            f"</div>"
        )

    mealie_html = ""
    if summary.mealie_today is not None:
        m_name = html.escape(summary.mealie_today.name)
        m_score = (
            f" · {summary.mealie_today.health_score}/100"
            if summary.mealie_today.health_score is not None
            else ""
        )
        mealie_html = (
            f'<div class="mealie-row">'
            f'<span class="k">HEUTE</span>'
            f'<span class="v">{m_name}{m_score}</span>'
            f"</div>"
        )

    sparkline_w = 130 if size == "sm" else (180 if size == "md" else 260)
    sparkline_h = 28 if size == "sm" else (38 if size == "md" else 48)
    sparkline_svg = _render_sparkline_svg(summary.trend_8_weeks, width=sparkline_w, height=sparkline_h)

    ratios_html = ""
    if cw is not None and size in ("md", "lg"):
        ratios_html = f"""
        <div class="ratios">
          <div class="ratio-cell"><div class="rk">PROTEIN</div><div class="rv">{cw.protein_per_1000_kcal:.0f}g</div></div>
          <div class="ratio-cell"><div class="rk">FRISCH</div><div class="rv">{cw.fresh_share_pct:.0f}%</div></div>
          <div class="ratio-cell"><div class="rk">NOVA 1–2</div><div class="rv">{cw.nova_1_2_share_pct:.0f}%</div></div>
          <div class="ratio-cell"><div class="rk">SNACKS</div><div class="rv">{cw.snack_share_pct:.0f}%</div></div>
        </div>
        """

    pad = "10px 12px" if size == "sm" else ("14px 16px" if size == "md" else "18px 22px")
    score_font = "34px" if size == "sm" else ("44px" if size == "md" else "54px")

    page = f"""<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Stats for Picnic · E-Ink</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html, body {{
      width: 100%; height: 100%;
      background: {bg}; color: {ink};
      font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif;
      font-variant-numeric: tabular-nums;
      -webkit-font-smoothing: none;
    }}
    .tile {{
      width: 100%; min-height: 100%;
      padding: {pad};
      display: flex; flex-direction: column; justify-content: space-between; gap: 10px;
      border: 1px solid {ink};
    }}
    .hdr {{
      display: flex; align-items: center; justify-content: space-between;
      border-bottom: 1px solid {ink}; padding-bottom: 6px;
      font-size: 11px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
    }}
    .badge {{
      border: 1px solid {ink}; padding: 1px 5px; font-size: 9px; font-weight: 700;
    }}
    .hero {{
      display: flex; align-items: flex-end; justify-content: space-between; gap: 12px;
    }}
    .score-num {{
      font-size: {score_font}; font-weight: 800; line-height: 0.95; letter-spacing: -0.03em;
    }}
    .score-max {{ font-size: 14px; font-weight: 600; color: {muted}; margin-left: 2px; }}
    .delta {{ font-size: 12px; font-weight: 700; margin-top: 4px; }}
    .bar-track {{
      width: 100%; height: 8px; border: 1px solid {ink}; background: transparent;
    }}
    .bar-fill {{
      height: 100%; width: {max(0, min(100, score_val))}%; background: {ink};
    }}
    .ratios {{
      display: grid; grid-template-columns: repeat(4, 1fr);
      border-top: 1px solid {rule}; border-bottom: 1px solid {rule};
    }}
    .ratio-cell {{
      padding: 6px 4px; border-right: 1px solid {rule}; text-align: left;
    }}
    .ratio-cell:last-child {{ border-right: none; }}
    .rk {{ font-size: 9px; font-weight: 700; letter-spacing: 0.06em; color: {muted}; }}
    .rv {{ font-size: 15px; font-weight: 800; margin-top: 2px; }}
    .cart-strip, .mealie-row {{
      display: flex; align-items: baseline; justify-content: space-between; gap: 8px;
      font-size: 11px; border-top: 1px solid {rule}; padding-top: 6px;
    }}
    .k {{ font-weight: 700; letter-spacing: 0.06em; color: {muted}; white-space: nowrap; }}
    .v {{ font-weight: 700; text-align: right; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .spark {{ display: flex; flex-direction: column; align-items: flex-end; gap: 2px; }}
    .spark-label {{ font-size: 9px; font-weight: 700; letter-spacing: 0.06em; color: {muted}; }}
  </style>
</head>
<body>
  <main class="tile">
    <header class="hdr">
      <span>PICNIC · {html.escape(week_label)}</span>
      <span>{status_badge}</span>
    </header>
    <section class="hero">
      <div>
        <div><span class="score-num">{score_val}</span><span class="score-max">/100</span></div>
        <div class="delta">{html.escape(delta_str)}</div>
      </div>
      <div class="spark">
        <span class="spark-label">8 WOCHEN</span>
        {sparkline_svg}
      </div>
    </section>
    <div class="bar-track"><div class="bar-fill"></div></div>
    {ratios_html}
    {cart_html if size != "sm" else ""}
    {mealie_html}
  </main>
</body>
</html>"""

    # Intentionally omit X-Frame-Options: DENY so Tesserae's Web widget can embed this page directly.
    return HTMLResponse(
        content=page,
        headers={
            "Cache-Control": "no-store",
        },
    )
