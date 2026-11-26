import type { BasketScoreResult } from '../api/client'

interface RatioItem {
  label: string
  value: string
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
      value: `${metrics.protein_per_1000_kcal.toFixed(1)} g / 1.000 kcal`,
      target: proteinGoal ? `Ziel ${proteinGoal.detail}` : 'Ziel ≥ 35 g',
      pct: Math.min(100, Math.max(4, metrics.sub_scores.protein_score)),
      tone: (proteinGoal ? proteinGoal.met : metrics.protein_per_1000_kcal >= 35) ? 'sage' : 'neutral',
    },
    {
      label: 'Frisch & Gemüse',
      value: `${metrics.fresh_share_pct.toFixed(0)} %`,
      target: freshGoal ? `Ziel ${freshGoal.detail}` : 'Ziel ≥ 35 %',
      pct: Math.min(100, Math.max(4, metrics.sub_scores.fresh_score)),
      tone: (freshGoal ? freshGoal.met : metrics.fresh_share_pct >= 35) ? 'sage' : 'neutral',
    },
    {
      label: 'Unverarbeitet (NOVA 1–2)',
      value: `${metrics.nova_1_2_share_pct.toFixed(0)} %`,
      target: novaGoal ? `Ziel ${novaGoal.detail}` : 'Ziel ≥ 75 %',
      pct: Math.min(100, Math.max(4, metrics.sub_scores.nova_score)),
      tone: (novaGoal ? novaGoal.met : metrics.nova_1_2_share_pct >= 75) ? 'sage' : 'neutral',
    },
    {
      label: 'Snacks & Zucker',
      value: `${metrics.snack_share_pct.toFixed(0)} %`,
      target: snackGoal ? `Ziel ${snackGoal.detail}` : 'Ziel ≤ 15 %',
      pct: Math.min(100, Math.max(4, metrics.snack_share_pct * 2.2)),
      tone: (snackGoal ? snackGoal.met : metrics.snack_share_pct <= 15) ? 'sage' : 'amber',
    },
  ]

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
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
            className="bg-[#FAF9F6] border border-[#E5E4DF] rounded-xl p-3.5"
          >
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-xs font-medium text-zinc-600">{item.label}</span>
              <span className="text-[11px] text-zinc-400 truncate">{item.target}</span>
            </div>
            <div className={`mt-1 text-base font-semibold tabular-nums ${valColor}`}>
              {item.value}
            </div>
            <div className="mt-2.5 h-1.5 w-full rounded-full bg-[#E9E7E0] overflow-hidden">
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
