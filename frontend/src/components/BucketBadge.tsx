import type { BucketType } from '../api/client'

export const BUCKET_LABELS: Record<BucketType | string, string> = {
  produce: 'Frisch',
  protein: 'Protein',
  whole_food: 'Vollwert',
  staple: 'Basis',
  treat_snack: 'Snack',
  beverage: 'Getränk',
  household: 'Haushalt',
}

const BUCKET_STYLES: Record<string, string> = {
  produce: 'bg-[#2E7D5B]/10 text-[#2E7D5B] border-[#2E7D5B]/20',
  protein: 'bg-emerald-50 text-emerald-800 border-emerald-200/80',
  whole_food: 'bg-stone-100 text-stone-700 border-stone-200',
  staple: 'bg-zinc-100 text-zinc-700 border-zinc-200/80',
  treat_snack: 'bg-[#D97706]/10 text-[#B45309] border-[#D97706]/25',
  beverage: 'bg-sky-50 text-sky-800 border-sky-200/80',
  household: 'bg-zinc-100 text-zinc-500 border-zinc-200',
}

export function BucketBadge({ bucket }: { bucket: string | null | undefined }) {
  const key = bucket || 'staple'
  const cls = BUCKET_STYLES[key] ?? BUCKET_STYLES.staple
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium border ${cls}`}
    >
      {BUCKET_LABELS[key] ?? key}
    </span>
  )
}

export function NovaBadge({ nova }: { nova: number | null | undefined }) {
  if (!nova) return null
  const cls =
    nova <= 2
      ? 'bg-[#2E7D5B]/8 text-[#2E7D5B] border-[#2E7D5B]/20'
      : nova === 3
        ? 'bg-zinc-100 text-zinc-600 border-zinc-200'
        : 'bg-[#D97706]/10 text-[#B45309] border-[#D97706]/25'
  return (
    <span
      className={`inline-flex items-center px-1.5 py-0.5 rounded-md text-[10px] font-semibold tracking-wide border tabular-nums ${cls}`}
    >
      NOVA {nova}
    </span>
  )
}
