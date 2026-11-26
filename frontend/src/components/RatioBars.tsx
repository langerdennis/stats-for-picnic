import type { BasketScoreResult } from '../api/client'

interface RatioItem {
  label: string
  shortLabel: string
  value: string
  shortValue: string
  target: string
  pct: number
  tone: 'sage' | 'amber' | 'neutral'
}

export function RatioBars({ metrics }: { metrics: BasketScoreResult }) {
  const goalMap = new Map(metrics.tier?.goals?.map((g) => [g.key, g]) ?? [])
  const proteinGoal = goalMap.get('protein')
  const freshGoal = goalMap.get('fresh')
  const novaGoal = goalMap.get('nova')
  const snackGoal = goalMap.get('snacks')

  const items: RatioItem[] = [
    {
      label: 'Proteindichte',
      shortLabel: 'Protein',
      value: `${metrics.protein_per_1000_kcal.toFixed(1)} g / 1.000 kcal`,
      shortValue: `${metrics.protein_per_1000_kcal.toFixed(0)} g/1k`,
      target: proteinGoal ? `Ziel ${proteinGoal.detail}` : 'Ziel ≥ 35 g',
      pct: Math.min(100, Math.max(4, metrics.sub_scores.protein_score)),
      tone: (proteinGoal ? proteinGoal.met : metrics.protein_per_1000_kcal >= 35) ? 'sage' : 'neutral',
    },
    {
      label: 'Frisch & Gemüse',
      shortLabel: 'Frisch',
      value: `${metrics.fresh_share_pct.toFixed(0)} %`,
      shortValue: `${metrics.fresh_share_pct.toFixed(0)} %`,
      target: freshGoal ? `Ziel ${freshGoal.detail}` : 'Ziel ≥ 35 %',
      pct: Math.min(100, Math.max(4, metrics.sub_scores.fresh_score)),
      tone: (freshGoal ? freshGoal.met : metrics.fresh_share_pct >= 35) ? 'sage' : 'neutral',
    },
    {
      label: 'Unverarbeitet (NOVA 1–2)',
      shortLabel: 'NOVA 1–2',
      value: `${metrics.nova_1_2_share_pct.toFixed(0)} %`,
      shortValue: `${metrics.nova_1_2_share_pct.toFixed(0)} %`,
      target: novaGoal ? `Ziel ${novaGoal.detail}` : 'Ziel ≥ 75 %',
      pct: Math.min(100, Math.max(4, metrics.sub_scores.nova_score)),
      tone: (novaGoal ? novaGoal.met : metrics.nova_1_2_share_pct >= 75) ? 'sage' : 'neutral',
    },
    {
      label: 'Snacks & Zucker',
      shortLabel: 'Snacks',
      value: `${metrics.snack_share_pct.toFixed(0)} %`,
      shortValue: `${metrics.snack_share_pct.toFixed(0)} %`,
      target: snackGoal ? `Ziel ${snackGoal.detail}` : 'Ziel ≤ 15 %',
      pct: Math.min(100, Math.max(4, metrics.snack_share_pct * 2.2)),
      tone: (snackGoal ? snackGoal.met : metrics.snack_share_pct <= 15) ? 'sage' : 'amber',
    },
  ]

  return (
    <div className="grid grid-cols-2 gap-2 sm:gap-3">
      {items.map((item) => {
        const barColor =
          item.tone === 'sage'
            ? 'bg-[#2E7D5B]'
            : item.tone === 'amber'
              ? 'bg-[#D97706]'
              : 'bg-zinc-500'
        const valColor = item.tone === 'amber' ? 'text-[#B45309]' : 'text-[#18181B]'
        return (
          <div
            key={item.label}
            className="bg-[#FAF9F6] border border-[#E5E4DF] rounded-xl p-2.5 sm:p-3.5"
          >
            <div className="flex items-baseline justify-between gap-1.5">
              <span className="text-[11px] sm:text-xs font-medium text-zinc-600 truncate">
                <span className="sm:hidden">{item.shortLabel}</span>
                <span className="hidden sm:inline">{item.label}</span>
              </span>
              <span className="text-[10px] sm:text-[11px] text-zinc-400 truncate hidden sm:inline">
                {item.target}
              </span>
            </div>
            <div className="mt-0.5 sm:mt-1 flex items-baseline justify-between gap-1">
              <div className={`text-sm sm:text-base font-semibold tabular-nums ${valColor}`}>
                <span className="sm:hidden">{item.shortValue}</span>
                <span className="hidden sm:inline">{item.value}</span>
              </div>
              <span className="text-[10px] text-zinc-400 truncate sm:hidden">
                {item.target.replace('Ziel ', '')}
              </span>
            </div>
            <div className="mt-1.5 sm:mt-2.5 h-1.5 w-full rounded-full bg-[#E9E7E0] overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-300 ${barColor}`}
                style={{ width: `${item.pct}%` }}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}
