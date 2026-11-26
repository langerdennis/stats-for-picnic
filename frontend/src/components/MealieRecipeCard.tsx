import { UtensilsCrossed } from 'lucide-react'
import { formatShortDate, type MealiePlanEntry } from '../api/client'

const ENTRY_TYPE_DE: Record<string, string> = {
  breakfast: 'Frühstück',
  lunch: 'Mittag',
  dinner: 'Abendessen',
  side: 'Beilage',
}

export function MealieRecipeCard({ entry }: { entry: MealiePlanEntry }) {
  const recipe = entry.recipe
  const score = recipe?.health_score
  const scoreTone =
    score != null && score >= 75
      ? 'bg-[#2E7D5B]/10 text-[#2E7D5B] border-[#2E7D5B]/20'
      : score != null && score >= 55
        ? 'bg-zinc-100 text-zinc-700 border-zinc-200'
        : 'bg-[#D97706]/10 text-[#B45309] border-[#D97706]/25'

  return (
    <div className="bg-white border border-[#E5E4DF] rounded-2xl overflow-hidden flex flex-col">
      <div className="relative aspect-[16/10] bg-[#F4F2EC] overflow-hidden">
        {recipe?.image_url ? (
          <img
            src={recipe.image_url}
            alt={recipe.name}
            loading="lazy"
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-zinc-400">
            <UtensilsCrossed className="w-7 h-7" />
          </div>
        )}
        {score != null && (
          <span
            className={`absolute top-2.5 right-2.5 px-2.5 py-1 rounded-full text-xs font-semibold border backdrop-blur-sm tabular-nums bg-white/90 ${scoreTone}`}
          >
            {score}/100
          </span>
        )}
      </div>

      <div className="p-3.5 flex-1 flex flex-col justify-between gap-2">
        <div>
          <div className="flex items-center justify-between gap-2 text-[11px] text-zinc-500">
            <span>{formatShortDate(entry.plan_date)}</span>
            <span>{ENTRY_TYPE_DE[entry.entry_type] ?? entry.entry_type}</span>
          </div>
          <h4 className="mt-1 font-semibold text-sm text-[#18181B] leading-snug line-clamp-2">
            {recipe?.name ?? entry.title}
          </h4>
          {recipe?.score_summary && (
            <p className="mt-1 text-xs text-zinc-500 leading-relaxed">{recipe.score_summary}</p>
          )}
        </div>

        {(recipe?.protein_level || recipe?.veggie_level) && (
          <div className="flex flex-wrap gap-1.5 pt-1">
            {recipe.protein_level && (
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-[#FAF9F6] border border-[#E5E4DF] text-zinc-600">
                Protein: {recipe.protein_level}
              </span>
            )}
            {recipe.veggie_level && (
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-[#FAF9F6] border border-[#E5E4DF] text-zinc-600">
                Gemüse: {recipe.veggie_level}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
