import { useState } from 'react'
import type { WeekTrendPoint } from '../api/client'

export function TrendChart({ points }: { points: WeekTrendPoint[] }) {
  const [activeIdx, setActiveIdx] = useState<number | null>(null)

  if (!points.length) {
    return (
      <div className="h-44 flex items-center justify-center text-sm text-zinc-400">
        Noch keine Wochendaten für den Verlauf vorhanden.
      </div>
    )
  }

  const width = 560
  const height = 185
  const padX = 28
  const padTop = 20
  const padBottom = 30

  const scores = points.map((p) => p.score)
  const minVal = Math.min(40, ...scores)
  const maxVal = Math.max(95, ...scores)
  const span = Math.max(10, maxVal - minVal)

  const coords = points.map((p, idx) => {
    const x =
      points.length === 1
        ? width / 2
        : padX + (idx / (points.length - 1)) * (width - 2 * padX)
    const y =
      height - padBottom - ((p.score - minVal) / span) * (height - padTop - padBottom)
    return { x, y, point: p }
  })

  const linePath = coords.map((c, i) => `${i === 0 ? 'M' : 'L'} ${c.x} ${c.y}`).join(' ')
  const areaPath =
    coords.length > 1
      ? `${linePath} L ${coords[coords.length - 1].x} ${height - padBottom} L ${coords[0].x} ${height - padBottom} Z`
      : ''

  const targetY =
    height - padBottom - ((75 - minVal) / span) * (height - padTop - padBottom)

  const highlighted = activeIdx !== null ? coords[activeIdx] : coords[coords.length - 1]

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-zinc-500">
          {highlighted.point.iso_week}
          {highlighted.point.fresh_share_pct != null && (
            <span className="ml-2 text-zinc-400">
              · Frisch {highlighted.point.fresh_share_pct.toFixed(0)} % · NOVA 1–2{' '}
              {highlighted.point.nova_1_2_share_pct?.toFixed(0) ?? '—'} %
            </span>
          )}
        </span>
        <span className="text-sm font-semibold text-[#2E7D5B] tabular-nums">
          Score {highlighted.point.score}/100
        </span>
      </div>

      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full h-44 overflow-visible"
        role="img"
        aria-label="8-Wochen Qualitätsverlauf"
      >
        <defs>
          <linearGradient id="sageFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#2E7D5B" stopOpacity="0.16" />
            <stop offset="100%" stopColor="#2E7D5B" stopOpacity="0.0" />
          </linearGradient>
        </defs>

        {/* Subtle target reference line at 75 */}
        <line
          x1={padX}
          y1={targetY}
          x2={width - padX}
          y2={targetY}
          stroke="#D6D3C9"
          strokeDasharray="4 4"
          strokeWidth="1"
        />
        <text
          x={width - padX}
          y={targetY - 5}
          textAnchor="end"
          className="fill-zinc-400 text-[10px]"
        >
          Ziel 75
        </text>

        {/* Area */}
        {areaPath && <path d={areaPath} fill="url(#sageFill)" />}

        {/* Trend line */}
        <path
          d={linePath}
          fill="none"
          stroke="#2E7D5B"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* Points */}
        {coords.map((c, idx) => {
          const isActive =
            activeIdx === idx || (activeIdx === null && idx === coords.length - 1)
          const wkShort = c.point.iso_week.split('-')[1] ?? c.point.iso_week
          return (
            <g
              key={c.point.iso_week}
              className="cursor-pointer"
              onMouseEnter={() => setActiveIdx(idx)}
              onMouseLeave={() => setActiveIdx(null)}
              onClick={() => setActiveIdx(idx)}
            >
              <circle cx={c.x} cy={c.y} r="14" fill="transparent" />
              <circle
                cx={c.x}
                cy={c.y}
                r={isActive ? 5 : 3.5}
                fill={isActive ? '#2E7D5B' : '#FFFFFF'}
                stroke="#2E7D5B"
                strokeWidth="2.2"
              />
              <text
                x={c.x}
                y={height - 8}
                textAnchor="middle"
                className={`text-[11px] tabular-nums ${
                  isActive ? 'fill-[#18181B] font-semibold' : 'fill-zinc-400'
                }`}
              >
                {wkShort}
              </text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}
