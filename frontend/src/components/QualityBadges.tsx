import { Award, Check, Flame } from 'lucide-react'
import type { QualityTier } from '../api/client'

export function TierPill({ tier }: { tier: QualityTier }) {
  const cls =
    tier.tone === 'sage'
      ? 'bg-[#2E7D5B]/10 text-[#2E7D5B] border-[#2E7D5B]/20'
      : tier.tone === 'amber'
        ? 'bg-[#D97706]/12 text-[#B45309] border-[#D97706]/25'
        : 'bg-zinc-100 text-zinc-700 border-zinc-200'

  return (
    <span
      className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold border ${cls}`}
    >
      {tier.label}
    </span>
  )
}

export function StreakAndBestBadges({
  streakWeeks,
  isPersonalBest,
}: {
  streakWeeks?: number
  isPersonalBest?: boolean
}) {
  const showStreak = (streakWeeks ?? 0) >= 2
  if (!showStreak && !isPersonalBest) return null

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {showStreak && (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-[#2E7D5B]/10 text-[#2E7D5B] border border-[#2E7D5B]/20 tabular-nums">
          <Flame className="w-3.5 h-3.5" />
          {streakWeeks} Wochen in Folge ≥ 75
        </span>
      )}
      {isPersonalBest && (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-[#18181B] text-white">
          <Award className="w-3.5 h-3.5" />
          8-Wochen-Bestwert
        </span>
      )}
    </div>
  )
}

export function GoalChecklist({ tier }: { tier: QualityTier }) {
  if (!tier.goals?.length) return null

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {tier.goals.map((g) => (
        <span
          key={g.key}
          title={g.detail}
          className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium border transition ${
            g.met
              ? 'bg-[#2E7D5B]/8 text-[#2E7D5B] border-[#2E7D5B]/25'
              : 'bg-[#FAF9F6] text-zinc-400 border-[#E5E4DF]'
          }`}
        >
          <span
            className={`w-3.5 h-3.5 rounded-full flex items-center justify-center ${
              g.met ? 'bg-[#2E7D5B] text-white' : 'border border-zinc-300'
            }`}
          >
            {g.met && <Check className="w-2.5 h-2.5 stroke-[3]" />}
          </span>
          {g.label}
        </span>
      ))}
      <span className="text-[11px] text-zinc-400 tabular-nums ml-1">
        {tier.goals_met}/{tier.goals_total} Ziele
      </span>
    </div>
  )
}
