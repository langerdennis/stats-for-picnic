import {
  ArrowDownRight,
  ArrowUpRight,
  Award,
  BarChart3,
  CalendarDays,
  ChevronDown,
  ChevronUp,
  Dumbbell,
  Plus,
  Search,
  Sparkles,
  TrendingUp,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import {
  api,
  formatEuro,
  type PeriodSpendScorePoint,
  type ProductPricePoint,
  type StatsRange,
  type StatsResponse,
} from '../api/client'
import { BUCKET_LABELS, BucketBadge } from './BucketBadge'
import { ProductThumb } from './ProductThumb'

interface Props {
  onAddToCart: (picnicId: string, name: string) => Promise<void>
  busyId: string | null
}

type SortKey = 'spend' | 'units' | 'weight'

const RANGE_OPTIONS: { key: StatsRange; label: string }[] = [
  { key: '30d', label: '30 Tage' },
  { key: '90d', label: '90 Tage' },
  { key: '1y', label: '1 Jahr' },
  { key: 'all', label: 'Gesamt' },
]

const BUCKET_COLORS: Record<string, string> = {
  produce: '#2E7D5B',
  protein: '#0F766E',
  whole_food: '#65A30D',
  staple: '#71717A',
  beverage: '#0284C7',
  treat_snack: '#D97706',
  household: '#A1A1AA',
}

function SpendScoreChart({ periods }: { periods: PeriodSpendScorePoint[] }) {
  const [activeIdx, setActiveIdx] = useState<number | null>(null)
  if (periods.length < 2) return null

  const width = 520
  const height = 180
  const padX = 28
  const padTop = 18
  const padBottom = 28
  const plotH = height - padTop - padBottom
  const plotW = width - padX * 2

  const maxSpend = Math.max(1000, ...periods.map((p) => p.spend_cents))
  const slotW = plotW / periods.length
  const barW = Math.min(30, Math.max(10, slotW * 0.56))

  const coords = periods.map((p, idx) => {
    const cx = padX + slotW * idx + slotW / 2
    const barH = Math.max(4, (p.spend_cents / maxSpend) * plotH)
    const barY = height - padBottom - barH
    const scoreY =
      p.avg_score != null
        ? height - padBottom - ((Math.max(30, Math.min(100, p.avg_score)) - 30) / 70) * plotH
        : null
    return { cx, barH, barY, scoreY, point: p }
  })

  const scoredCoords = coords.filter((c): c is typeof c & { scoreY: number } => c.scoreY !== null)
  const scorePath = scoredCoords
    .map((c, i) => `${i === 0 ? 'M' : 'L'} ${c.cx.toFixed(1)} ${c.scoreY.toFixed(1)}`)
    .join(' ')

  const highlighted = activeIdx !== null ? coords[activeIdx] : coords[coords.length - 1]

  return (
    <div>
      <div className="flex items-center justify-between gap-2 mb-2 text-xs">
        <span className="text-zinc-500 font-medium">{highlighted.point.label}</span>
        <div className="flex items-center gap-3 tabular-nums">
          <span className="font-semibold text-[#18181B]">
            {formatEuro(highlighted.point.spend_cents)}
          </span>
          {highlighted.point.avg_score != null && (
            <span className="font-semibold text-[#2E7D5B]">
              Score {highlighted.point.avg_score}/100
            </span>
          )}
        </div>
      </div>

      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full h-44 overflow-visible"
        role="img"
        aria-label="Ausgaben und Score im Verlauf"
      >
        {[0.25, 0.5, 0.75, 1].map((frac) => {
          const y = height - padBottom - frac * plotH
          return (
            <line
              key={frac}
              x1={padX}
              y1={y}
              x2={width - padX}
              y2={y}
              stroke="#ECEBE6"
              strokeDasharray="3 3"
              strokeWidth="1"
            />
          )
        })}

        {coords.map((c, idx) => {
          const isActive =
            activeIdx === idx || (activeIdx === null && idx === coords.length - 1)
          return (
            <g
              key={c.point.period_key}
              className="cursor-pointer"
              onMouseEnter={() => setActiveIdx(idx)}
              onMouseLeave={() => setActiveIdx(null)}
              onClick={() => setActiveIdx(idx)}
            >
              <rect
                x={c.cx - slotW / 2}
                y={padTop}
                width={slotW}
                height={plotH + padBottom}
                fill="transparent"
              />
              <rect
                x={c.cx - barW / 2}
                y={c.barY}
                width={barW}
                height={c.barH}
                rx="5"
                fill={isActive ? '#C7C3B8' : '#E5E3DC'}
              />
              <text
                x={c.cx}
                y={height - 8}
                textAnchor="middle"
                className={`text-[10px] tabular-nums ${
                  isActive ? 'fill-[#18181B] font-semibold' : 'fill-zinc-400'
                }`}
              >
                {c.point.label.replace('KW ', 'W')}
              </text>
            </g>
          )
        })}

        {scorePath && (
          <path
            d={scorePath}
            fill="none"
            stroke="#2E7D5B"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="pointer-events-none"
          />
        )}
        {scoredCoords.map((c) => {
          const idx = coords.indexOf(c)
          const isActive =
            activeIdx === idx || (activeIdx === null && idx === coords.length - 1)
          return (
            <circle
              key={`pt-${c.point.period_key}`}
              cx={c.cx}
              cy={c.scoreY}
              r={isActive ? 4.5 : 3}
              fill={isActive ? '#2E7D5B' : '#FFFFFF'}
              stroke="#2E7D5B"
              strokeWidth="2"
              className="pointer-events-none"
            />
          )
        })}
      </svg>
    </div>
  )
}

function MiniPriceSparkline({ points }: { points: ProductPricePoint[] }) {
  if (points.length < 2) return null
  const prices = points.map((p) => p.unit_price_cents)
  const minP = Math.min(...prices)
  const maxP = Math.max(...prices)
  const span = Math.max(10, maxP - minP)
  const w = 160
  const h = 34
  const pad = 4

  const coords = points.map((pt, idx) => {
    const x = pad + (idx / Math.max(1, points.length - 1)) * (w - pad * 2)
    const y = h - pad - ((pt.unit_price_cents - minP) / span) * (h - pad * 2)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })
  const rising = prices[prices.length - 1] > prices[0]
  const falling = prices[prices.length - 1] < prices[0]
  const stroke = rising ? '#D97706' : falling ? '#2E7D5B' : '#71717A'

  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="overflow-visible">
      <polyline
        fill="none"
        stroke={stroke}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={coords.join(' ')}
      />
      {points.map((pt, idx) => {
        const [cx, cy] = coords[idx].split(',')
        return <circle key={`${pt.date}-${idx}`} cx={cx} cy={cy} r="2.2" fill={stroke} />
      })}
    </svg>
  )
}

export function StatsView({ onAddToCart, busyId }: Props) {
  const [range, setRange] = useState<StatsRange>('90d')
  const [stats, setStats] = useState<StatsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sortBy, setSortBy] = useState<SortKey>('spend')
  const [query, setQuery] = useState('')
  const [showAllProducts, setShowAllProducts] = useState(false)
  const [expandedPid, setExpandedPid] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    setLoading(true)
    setError(null)
    api
      .getStats(range)
      .then((res) => {
        if (active) setStats(res)
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : 'Statistiken nicht ladbar')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [range])

  const filteredProducts = useMemo(() => {
    if (!stats) return []
    const needle = query.trim().toLowerCase()
    const base = needle
      ? stats.products.filter(
          (p) =>
            p.name.toLowerCase().includes(needle) ||
            (BUCKET_LABELS[p.bucket] ?? p.bucket).toLowerCase().includes(needle),
        )
      : stats.products

    const copy = [...base]
    if (sortBy === 'units') {
      copy.sort((a, b) => b.total_units - a.total_units || b.total_spend_cents - a.total_spend_cents)
    } else if (sortBy === 'weight') {
      copy.sort(
        (a, b) => b.total_weight_kg - a.total_weight_kg || b.total_spend_cents - a.total_spend_cents,
      )
    } else {
      copy.sort((a, b) => b.total_spend_cents - a.total_spend_cents || b.total_units - a.total_units)
    }
    return copy
  }, [stats, query, sortBy])

  const searchSummary = useMemo(() => {
    if (!query.trim()) return null
    const cents = filteredProducts.reduce((acc, p) => acc + p.total_spend_cents, 0)
    const units = filteredProducts.reduce((acc, p) => acc + p.total_units, 0)
    const kg = filteredProducts.reduce((acc, p) => acc + p.total_weight_kg, 0)
    return { count: filteredProducts.length, cents, units, kg }
  }, [filteredProducts, query])

  if (loading && !stats) {
    return (
      <div className="space-y-4 animate-pulse">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-24 rounded-2xl bg-white border border-[#E5E4DF]" />
          ))}
        </div>
        <div className="h-64 rounded-2xl bg-white border border-[#E5E4DF]" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-[#D97706]/10 border border-[#D97706]/30 text-[#92400E] rounded-2xl p-4 text-sm">
        {error}
      </div>
    )
  }

  if (!stats || stats.summary.delivery_count === 0) {
    return (
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-xs text-zinc-500">Zeitraum wählen</span>
          <div className="inline-flex p-1 rounded-xl bg-white border border-[#E5E4DF] gap-0.5">
            {RANGE_OPTIONS.map((opt) => (
              <button
                key={opt.key}
                type="button"
                onClick={() => setRange(opt.key)}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition cursor-pointer ${
                  range === opt.key ? 'bg-[#18181B] text-white' : 'text-zinc-600 hover:bg-[#FAF9F6]'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
        <div className="bg-white border border-[#E5E4DF] rounded-2xl p-8 text-center text-sm text-zinc-500">
          Keine Lieferungen im gewählten Zeitraum gefunden.
        </div>
      </div>
    )
  }

  const { summary, buckets, periods, price_changes, protein_value_leaders, habits } = stats
  const visibleProducts = showAllProducts || query.trim() ? filteredProducts : filteredProducts.slice(0, 8)
  const maxWeekdayCount = Math.max(1, ...habits.weekday_distribution.map((w) => w.count))
  const totalFoodAndNonFood = Math.max(1, summary.food_spend_cents + summary.non_food_spend_cents)
  const nonFoodPct = Math.round((summary.non_food_spend_cents / totalFoodAndNonFood) * 100)

  return (
    <div className={`space-y-4 ${loading ? 'opacity-70 transition-opacity' : ''}`}>
      {/* Range Selector */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-zinc-500">
          Auswertung aus <strong className="text-[#18181B]">{summary.delivery_count}</strong>{' '}
          {summary.delivery_count === 1 ? 'Lieferung' : 'Lieferungen'} ·{' '}
          <strong className="text-[#18181B]">{summary.unique_products}</strong> verschiedene Produkte
        </p>
        <div className="inline-flex p-1 rounded-xl bg-white border border-[#E5E4DF] gap-0.5">
          {RANGE_OPTIONS.map((opt) => (
            <button
              key={opt.key}
              type="button"
              onClick={() => setRange(opt.key)}
              className={`px-2.5 sm:px-3 py-1 rounded-lg text-xs font-medium transition cursor-pointer ${
                range === opt.key ? 'bg-[#18181B] text-white' : 'text-zinc-600 hover:bg-[#FAF9F6]'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* 4 Calm KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-white border border-[#E5E4DF] rounded-2xl p-4">
          <div className="text-[11px] font-medium text-zinc-400">Gesamtausgaben</div>
          <div className="mt-1 text-xl font-semibold text-[#18181B] tabular-nums">
            {formatEuro(summary.total_spend_cents)}
          </div>
          <div className="mt-1 text-[11px] text-zinc-500 tabular-nums">
            Ø {formatEuro(summary.avg_spend_per_delivery_cents)} / Bestellung
          </div>
        </div>

        <div className="bg-white border border-[#E5E4DF] rounded-2xl p-4">
          <div className="text-[11px] font-medium text-zinc-400">Ø pro Woche</div>
          <div className="mt-1 text-xl font-semibold text-[#18181B] tabular-nums">
            {formatEuro(summary.avg_spend_per_week_cents)}
          </div>
          <div className="mt-1 text-[11px] text-zinc-500 tabular-nums">
            davon {nonFoodPct} % Haushalt / Non-Food
          </div>
        </div>

        <div className="bg-white border border-[#E5E4DF] rounded-2xl p-4">
          <div className="text-[11px] font-medium text-zinc-400">Lebensmittel-Menge</div>
          <div className="mt-1 text-xl font-semibold text-[#18181B] tabular-nums">
            {summary.total_food_weight_kg.toFixed(1).replace('.', ',')} kg
          </div>
          <div className="mt-1 text-[11px] text-zinc-500 truncate">
            {habits.heaviest_product_name
              ? `Nr. 1: ${habits.heaviest_product_kg.toFixed(1).replace('.', ',')} kg ${habits.heaviest_product_name}`
              : `${summary.total_item_units} Artikel gesamt`}
          </div>
        </div>

        <div className="bg-white border border-[#E5E4DF] rounded-2xl p-4">
          <div className="text-[11px] font-medium text-zinc-400">Gesundheits-Euro-Quote</div>
          <div className="mt-1 text-xl font-semibold text-[#2E7D5B] tabular-nums">
            {Math.round(summary.healthy_spend_share_pct)} %
          </div>
          <div className="mt-1 text-[11px] text-zinc-500 tabular-nums">
            Frisch & Protein · Snacks {Math.round(summary.snack_spend_share_pct)} %
          </div>
        </div>
      </div>

      {/* Main 2-Column Foldable Split */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-4 items-start">
        {/* Left Column: Category Spend + Spend vs. Score Trend */}
        <div className="md:col-span-6 space-y-4">
          {/* Category / Bucket Spend Breakdown */}
          <section className="bg-white border border-[#E5E4DF] rounded-2xl p-4 sm:p-5 space-y-3.5">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <BarChart3 className="w-4 h-4 text-[#2E7D5B]" />
                <h3 className="text-sm font-semibold text-[#18181B]">Ausgaben nach Kategorie</h3>
              </div>
              {summary.avg_score != null && (
                <span className="text-xs font-medium text-[#2E7D5B] tabular-nums">
                  Ø Score {summary.avg_score}/100
                </span>
              )}
            </div>

            {/* Stacked Share Bar */}
            <div className="h-3 w-full rounded-full overflow-hidden flex bg-[#ECEBE6]">
              {buckets.map((b) => (
                <div
                  key={b.bucket}
                  style={{
                    width: `${Math.max(2, b.share_pct)}%`,
                    backgroundColor: BUCKET_COLORS[b.bucket] ?? '#71717A',
                  }}
                  title={`${BUCKET_LABELS[b.bucket] ?? b.bucket}: ${formatEuro(b.spend_cents)} (${b.share_pct}%)`}
                />
              ))}
            </div>

            <div className="divide-y divide-[#ECEBE6]">
              {buckets.map((b) => (
                <div
                  key={b.bucket}
                  className="py-2 flex items-center justify-between gap-2 text-xs"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <span
                      className="w-2.5 h-2.5 rounded-full shrink-0"
                      style={{ backgroundColor: BUCKET_COLORS[b.bucket] ?? '#71717A' }}
                    />
                    <span className="font-medium text-[#18181B] truncate">
                      {BUCKET_LABELS[b.bucket] ?? b.bucket}
                    </span>
                    <span className="text-zinc-400 tabular-nums shrink-0">
                      {b.weight_kg.toFixed(1).replace('.', ',')} kg
                    </span>
                  </div>
                  <div className="flex items-center gap-2.5 shrink-0 tabular-nums">
                    <span className="text-zinc-400">{Math.round(b.share_pct)} %</span>
                    <span className="font-semibold text-[#18181B] w-16 text-right">
                      {formatEuro(b.spend_cents)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Spend vs. Score Trend */}
          {periods.length >= 2 && (
            <section className="bg-white border border-[#E5E4DF] rounded-2xl p-4 sm:p-5 space-y-3">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <TrendingUp className="w-4 h-4 text-[#2E7D5B]" />
                  <h3 className="text-sm font-semibold text-[#18181B]">Ausgaben & Score</h3>
                </div>
                <div className="flex items-center gap-3 text-[11px] text-zinc-500">
                  <span className="inline-flex items-center gap-1">
                    <span className="w-2.5 h-2.5 rounded-sm bg-[#E5E3DC]" />
                    Ausgaben (€)
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <span className="w-2.5 h-0.5 bg-[#2E7D5B]" />
                    Score
                  </span>
                </div>
              </div>

              <SpendScoreChart periods={periods} />
            </section>
          )}
        </div>

        {/* Right Column: Searchable Per-Product Spending / Units / Weight Ranking */}
        <section className="md:col-span-6 bg-white border border-[#E5E4DF] rounded-2xl p-4 sm:p-5 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 className="text-sm font-semibold text-[#18181B]">Ausgaben nach Lebensmittel</h3>
              <p className="text-[11px] text-zinc-400">
                Nur mehrfach gekaufte Produkte (≥ 2 Lieferungen)
              </p>
            </div>
            <div className="inline-flex p-0.5 rounded-lg bg-[#FAF9F6] border border-[#E5E4DF] text-[11px]">
              {(
                [
                  ['spend', '€'],
                  ['units', '×'],
                  ['weight', 'kg'],
                ] as [SortKey, string][]
              ).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setSortBy(key)}
                  className={`px-2.5 py-1 rounded-md font-semibold transition cursor-pointer ${
                    sortBy === key ? 'bg-[#18181B] text-white' : 'text-zinc-600'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* Search any food to see total spend */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-zinc-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Lebensmittel nachschlagen (z. B. Lachs, Skyr, Käse)…"
              className="w-full pl-8 pr-3 py-2 text-xs sm:text-sm rounded-xl border border-[#E5E4DF] bg-[#FAF9F6] focus:bg-white focus:outline-none focus:border-[#2E7D5B]"
            />
          </div>

          {searchSummary && (
            <div className="px-3 py-2 rounded-xl bg-[#2E7D5B]/8 border border-[#2E7D5B]/20 flex flex-wrap items-center justify-between gap-2 text-xs text-[#1F5A41] tabular-nums">
              <span>
                <strong>{searchSummary.count}</strong> Treffer für „{query.trim()}“
              </span>
              <span className="font-semibold">
                {formatEuro(searchSummary.cents)} · {searchSummary.units}× ·{' '}
                {searchSummary.kg.toFixed(1).replace('.', ',')} kg
              </span>
            </div>
          )}

          <div className="divide-y divide-[#ECEBE6]">
            {visibleProducts.length === 0 ? (
              <p className="py-6 text-xs text-zinc-400 text-center">Keine passenden Produkte.</p>
            ) : (
              visibleProducts.map((p) => {
                const isExpanded = expandedPid === p.picnic_id
                return (
                  <div key={p.picnic_id} className="py-2.5">
                    <div className="flex items-center justify-between gap-2">
                      <button
                        type="button"
                        onClick={() => setExpandedPid(isExpanded ? null : p.picnic_id)}
                        className="flex items-center gap-2.5 min-w-0 flex-1 text-left cursor-pointer"
                      >
                        <ProductThumb src={p.image_url} alt={p.name} size="sm" />
                        <div className="min-w-0 flex-1">
                          <div className="text-sm font-medium text-[#18181B] truncate">
                            {p.name}
                          </div>
                          <div className="mt-0.5 flex items-center flex-wrap gap-x-2 gap-y-0.5 text-[11px] text-zinc-500 tabular-nums">
                            <span>{p.total_units}× gekauft</span>
                            <span>· {p.total_weight_kg.toFixed(1).replace('.', ',')} kg</span>
                            <span>· Ø {formatEuro(p.avg_unit_price_cents)}</span>
                            {p.price_change_pct != null && Math.abs(p.price_change_pct) >= 3 && (
                              <span
                                className={
                                  p.price_change_pct > 0
                                    ? 'text-[#B45309] font-medium'
                                    : 'text-[#2E7D5B] font-medium'
                                }
                              >
                                {p.price_change_pct > 0 ? '+' : ''}
                                {Math.round(p.price_change_pct)} %
                              </span>
                            )}
                          </div>
                        </div>
                      </button>

                      <div className="shrink-0 flex items-center gap-2">
                        <div className="text-right tabular-nums">
                          <div className="text-sm font-semibold text-[#18181B]">
                            {sortBy === 'units'
                              ? `${p.total_units}×`
                              : sortBy === 'weight'
                                ? `${p.total_weight_kg.toFixed(1).replace('.', ',')} kg`
                                : formatEuro(p.total_spend_cents)}
                          </div>
                          {sortBy !== 'spend' && (
                            <div className="text-[10px] text-zinc-400">
                              {formatEuro(p.total_spend_cents)}
                            </div>
                          )}
                        </div>
                        <button
                          type="button"
                          disabled={busyId === p.picnic_id}
                          onClick={() => onAddToCart(p.picnic_id, p.name)}
                          title="In Picnic-Warenkorb legen"
                          className="w-8 h-8 rounded-lg border border-[#E5E4DF] bg-[#FAF9F6] hover:bg-[#2E7D5B] hover:text-white hover:border-[#2E7D5B] text-zinc-700 flex items-center justify-center transition cursor-pointer disabled:opacity-50"
                        >
                          <Plus className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>

                    {isExpanded && (
                      <div className="mt-2.5 ml-11 p-3 rounded-xl bg-[#FAF9F6] border border-[#E5E4DF] flex flex-wrap items-center justify-between gap-3 text-xs">
                        <div className="space-y-1">
                          <div className="flex items-center gap-1.5">
                            <BucketBadge bucket={p.bucket} />
                            {p.unit_quantity && (
                              <span className="text-zinc-500">{p.unit_quantity}</span>
                            )}
                          </div>
                          <div className="text-[11px] text-zinc-500 tabular-nums">
                            In {p.delivery_hits} Lieferungen · letzter Preis:{' '}
                            <strong className="text-[#18181B]">
                              {formatEuro(p.latest_unit_price_cents)}
                            </strong>
                          </div>
                        </div>
                        {p.price_history.length >= 2 && (
                          <div className="flex flex-col items-end">
                            <span className="text-[10px] text-zinc-400 mb-0.5">
                              Stückpreis-Verlauf
                            </span>
                            <MiniPriceSparkline points={p.price_history} />
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })
            )}
          </div>

          {!query.trim() && filteredProducts.length > 8 && (
            <button
              type="button"
              onClick={() => setShowAllProducts((v) => !v)}
              className="w-full py-2 rounded-xl border border-[#E5E4DF] bg-[#FAF9F6] hover:bg-zinc-100 text-xs font-medium text-zinc-600 inline-flex items-center justify-center gap-1 cursor-pointer"
            >
              {showAllProducts ? (
                <>
                  Weniger anzeigen <ChevronUp className="w-3.5 h-3.5" />
                </>
              ) : (
                <>
                  Alle {filteredProducts.length} Produkte anzeigen{' '}
                  <ChevronDown className="w-3.5 h-3.5" />
                </>
              )}
            </button>
          )}
        </section>
      </div>

      {/* Bottom 3-Column Insights: Price Changes, Protein Value, Shopping Habits */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* 1) Price Tracker / Picnic Inflation */}
        <section className="bg-white border border-[#E5E4DF] rounded-2xl p-4 sm:p-5 space-y-3">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-[#D97706]" />
            <h3 className="text-sm font-semibold text-[#18181B]">Preisänderungen</h3>
          </div>
          {price_changes.length === 0 ? (
            <p className="text-xs text-zinc-400 leading-relaxed">
              Noch keine nennenswerten Stückpreis-Änderungen (≥ 3 %) im gewählten Zeitraum erkannt.
            </p>
          ) : (
            <div className="divide-y divide-[#ECEBE6]">
              {price_changes.slice(0, 5).map((pc) => {
                const up = pc.delta_cents > 0
                return (
                  <div key={pc.picnic_id} className="py-2 flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <div className="text-xs font-medium text-[#18181B] truncate">{pc.name}</div>
                      <div className="text-[11px] text-zinc-500 tabular-nums">
                        {formatEuro(pc.first_price_cents)} →{' '}
                        <strong className="text-[#18181B]">
                          {formatEuro(pc.latest_price_cents)}
                        </strong>
                      </div>
                    </div>
                    <span
                      className={`shrink-0 inline-flex items-center gap-0.5 px-2 py-0.5 rounded-full text-[11px] font-semibold tabular-nums ${
                        up
                          ? 'bg-[#D97706]/12 text-[#B45309]'
                          : 'bg-[#2E7D5B]/10 text-[#2E7D5B]'
                      }`}
                    >
                      {up ? (
                        <ArrowUpRight className="w-3 h-3" />
                      ) : (
                        <ArrowDownRight className="w-3 h-3" />
                      )}
                      {up ? '+' : ''}
                      {Math.round(pc.delta_pct)} %
                    </span>
                  </div>
                )
              })}
            </div>
          )}
        </section>

        {/* 2) Protein per Euro */}
        <section className="bg-white border border-[#E5E4DF] rounded-2xl p-4 sm:p-5 space-y-3">
          <div className="flex items-center gap-2">
            <Dumbbell className="w-4 h-4 text-[#2E7D5B]" />
            <h3 className="text-sm font-semibold text-[#18181B]">Protein pro Euro</h3>
          </div>
          {protein_value_leaders.length === 0 ? (
            <p className="text-xs text-zinc-400">
              Noch keine angereicherten Protein-Produkte im Zeitraum.
            </p>
          ) : (
            <div className="divide-y divide-[#ECEBE6]">
              {protein_value_leaders.slice(0, 5).map((pv) => (
                <div key={pv.picnic_id} className="py-2 flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-xs font-medium text-[#18181B] truncate">{pv.name}</div>
                    <div className="text-[11px] text-zinc-500 tabular-nums">
                      {Math.round(pv.protein_g_per_unit)} g / Packung · Ø{' '}
                      {formatEuro(pv.avg_unit_price_cents)}
                    </div>
                  </div>
                  <div className="shrink-0 flex items-center gap-1.5">
                    <span className="px-2 py-0.5 rounded-full bg-[#2E7D5B]/10 text-[#2E7D5B] text-[11px] font-semibold tabular-nums">
                      {pv.protein_g_per_euro.toFixed(0)} g/€
                    </span>
                    <button
                      type="button"
                      disabled={busyId === pv.picnic_id}
                      onClick={() => onAddToCart(pv.picnic_id, pv.name)}
                      title="In Picnic-Warenkorb legen"
                      className="w-7 h-7 rounded-lg border border-[#E5E4DF] bg-[#FAF9F6] hover:bg-[#2E7D5B] hover:text-white text-zinc-600 flex items-center justify-center cursor-pointer disabled:opacity-50"
                    >
                      <Plus className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* 3) Shopping Rhythm & Wrapped Highlights */}
        <section className="bg-white border border-[#E5E4DF] rounded-2xl p-4 sm:p-5 space-y-3">
          <div className="flex items-center gap-2">
            <CalendarDays className="w-4 h-4 text-[#2E7D5B]" />
            <h3 className="text-sm font-semibold text-[#18181B]">Einkaufs-Rhythmus</h3>
          </div>

          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="p-2.5 rounded-xl bg-[#FAF9F6] border border-[#E5E4DF]">
              <div className="text-[10px] text-zinc-400">Bestell-Abstand</div>
              <div className="mt-0.5 font-semibold text-[#18181B] tabular-nums">
                {habits.avg_days_between_deliveries != null
                  ? `alle ${habits.avg_days_between_deliveries.toFixed(1).replace('.', ',')} Tage`
                  : '—'}
              </div>
            </div>
            <div className="p-2.5 rounded-xl bg-[#FAF9F6] border border-[#E5E4DF]">
              <div className="text-[10px] text-zinc-400">Stammprodukte</div>
              <div className="mt-0.5 font-semibold text-[#18181B] tabular-nums">
                {Math.round(summary.repeat_purchase_share_pct)} % Anteil
              </div>
            </div>
          </div>

          {/* Mini Weekday Bar Distribution */}
          <div className="space-y-1">
            <div className="flex items-center justify-between text-[11px] text-zinc-500">
              <span>Liefertage</span>
              {habits.favorite_weekday && (
                <span className="font-medium text-[#18181B]">
                  Meistens {habits.favorite_weekday}
                </span>
              )}
            </div>
            <div className="grid grid-cols-7 gap-1.5 items-end h-12 pt-1">
              {habits.weekday_distribution.map((w) => {
                const hPct = w.count > 0 ? Math.max(18, Math.round((w.count / maxWeekdayCount) * 100)) : 8
                return (
                  <div key={w.day} className="flex flex-col items-center gap-1 h-full justify-end">
                    <div
                      className={`w-full rounded-sm ${
                        w.count === maxWeekdayCount && w.count > 0 ? 'bg-[#2E7D5B]' : 'bg-[#E5E4DF]'
                      }`}
                      style={{ height: `${hPct}%` }}
                      title={`${w.day}: ${w.count}×`}
                    />
                    <span className="text-[10px] text-zinc-400">{w.day}</span>
                  </div>
                )
              })}
            </div>
          </div>

          {/* Wrapped Highlights */}
          <div className="pt-2 border-t border-[#ECEBE6] space-y-1.5 text-xs text-zinc-600">
            {habits.most_bought_product_name && (
              <div className="flex items-center justify-between gap-2">
                <span className="inline-flex items-center gap-1 text-zinc-400 shrink-0">
                  <Award className="w-3 h-3 text-[#2E7D5B]" />
                  Meistgekauft
                </span>
                <span className="font-medium text-[#18181B] truncate tabular-nums">
                  {habits.most_bought_product_units}× {habits.most_bought_product_name}
                </span>
              </div>
            )}
            <div className="flex items-center justify-between gap-2 tabular-nums">
              <span className="text-zinc-400">Spanne / Einkauf</span>
              <span className="font-medium text-[#18181B]">
                {formatEuro(habits.smallest_delivery_cents)} –{' '}
                {formatEuro(habits.largest_delivery_cents)}
              </span>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}
