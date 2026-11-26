import { ArrowDownRight, ArrowUpRight } from 'lucide-react'
import type { ScoreDriver } from '../api/client'

export function DriversCard({
  positive,
  negative,
}: {
  positive: ScoreDriver[]
  negative: ScoreDriver[]
}) {
  if (!positive.length && !negative.length) return null

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
      <div className="bg-white border border-[#E5E4DF] rounded-2xl p-4">
        <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-[#2E7D5B]">
          <ArrowUpRight className="w-4 h-4" />
          Starke Treiber
        </div>
        {positive.length === 0 ? (
          <p className="mt-2 text-xs text-zinc-400">Noch keine positiven Treiber erkannt.</p>
        ) : (
          <ul className="mt-2.5 space-y-2">
            {positive.map((d) => (
              <li
                key={`pos-${d.picnic_id}`}
                className="flex items-start justify-between gap-2 text-sm"
              >
                <div>
                  <div className="font-medium text-[#18181B]">{d.name}</div>
                  <div className="text-xs text-zinc-500">{d.reason}</div>
                </div>
                <span className="text-xs text-zinc-400 tabular-nums shrink-0">
                  {Math.round(d.weight_g)} g
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="bg-white border border-[#E5E4DF] rounded-2xl p-4">
        <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-[#B45309]">
          <ArrowDownRight className="w-4 h-4" />
          Bremser
        </div>
        {negative.length === 0 ? (
          <p className="mt-2 text-xs text-zinc-500">
            Keine nennenswerten Snack- oder NOVA-4-Bremser enthalten.
          </p>
        ) : (
          <ul className="mt-2.5 space-y-2">
            {negative.map((d) => (
              <li
                key={`neg-${d.picnic_id}`}
                className="flex items-start justify-between gap-2 text-sm"
              >
                <div>
                  <div className="font-medium text-[#18181B]">{d.name}</div>
                  <div className="text-xs text-zinc-500">{d.reason}</div>
                </div>
                <span className="text-xs text-zinc-400 tabular-nums shrink-0">
                  {Math.round(d.weight_g)} g
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
