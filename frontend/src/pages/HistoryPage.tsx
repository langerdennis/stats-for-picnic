import {
  BarChart3,
  ChevronDown,
  ChevronUp,
  Eye,
  EyeOff,
  Plus,
  Receipt,
  Utensils,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import {
  api,
  formatEuro,
  formatShortDate,
  type Delivery,
  type MealiePlanEntry,
} from '../api/client'
import { BucketBadge, NovaBadge } from '../components/BucketBadge'
import { MealieRecipeCard } from '../components/MealieRecipeCard'
import { ProductThumb } from '../components/ProductThumb'
import { StatsView } from '../components/StatsView'

type HistorySubTab = 'deliveries' | 'stats'

interface Props {
  initialSubTab?: HistorySubTab
  onSubTabChange?: (sub: HistorySubTab) => void
  onCartCountChange?: (count: number) => void
}

export function HistoryPage({
  initialSubTab = 'deliveries',
  onSubTabChange,
  onCartCountChange,
}: Props) {
  const [subTab, setSubTab] = useState<HistorySubTab>(initialSubTab)
  const [deliveries, setDeliveries] = useState<Delivery[]>([])
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [mealieByWeek, setMealieByWeek] = useState<Record<string, MealiePlanEntry[]>>({})
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)

  useEffect(() => {
    setSubTab(initialSubTab)
  }, [initialSubTab])

  const switchSubTab = (next: HistorySubTab) => {
    setSubTab(next)
    onSubTabChange?.(next)
  }

  const showToast = (msg: string) => {
    setToast(msg)
    setTimeout(() => setToast((cur) => (cur === msg ? null : cur)), 2500)
  }

  const loadDeliveries = async (autoExpand = false) => {
    try {
      const list = await api.getDeliveries()
      setDeliveries(list)
      if (autoExpand && list.length > 0) {
        setExpandedId(list[0].delivery_id)
        void fetchMealieWeek(list[0].iso_week)
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadDeliveries(true)
  }, [])

  const fetchMealieWeek = async (isoWeek: string) => {
    if (mealieByWeek[isoWeek]) return
    try {
      const entries = await api.getMealieWeek(isoWeek)
      setMealieByWeek((prev) => ({ ...prev, [isoWeek]: entries }))
    } catch {
      // optional Mealie degradation
    }
  }

  const toggleExpand = (d: Delivery) => {
    if (expandedId === d.delivery_id) {
      setExpandedId(null)
    } else {
      setExpandedId(d.delivery_id)
      void fetchMealieWeek(d.iso_week)
    }
  }

  const handleReAdd = async (picnicId: string, name: string) => {
    setBusyId(picnicId)
    try {
      const updated = await api.addToCart(picnicId, 1)
      onCartCountChange?.(updated.item_count)
      showToast(`${name} (+1) in den Warenkorb gelegt`)
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Konnte nicht hinzugefügt werden')
    } finally {
      setBusyId(null)
    }
  }

  const handleToggleIgnore = async (picnicId: string, name: string, currentlyIgnored: boolean) => {
    setBusyId(picnicId)
    try {
      await api.updateProduct(
        picnicId,
        currentlyIgnored
          ? { ignored: false, ignored_reason: null }
          : { ignored: true, ignored_reason: 'family' },
      )
      await loadDeliveries(false)
      showToast(currentlyIgnored ? `${name} wieder einbezogen` : `${name} als Familie ignoriert`)
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Änderung fehlgeschlagen')
    } finally {
      setBusyId(null)
    }
  }

  // Calm 8-week household context (weekly spend + average score)
  const recentDeliveries = deliveries.slice(0, 8)
  const uniqueWeeks = new Set(recentDeliveries.map((d) => d.iso_week)).size || 1
  const totalRecentCents = recentDeliveries.reduce((acc, d) => acc + d.total_price_cents, 0)
  const avgWeeklyCents = Math.round(totalRecentCents / uniqueWeeks)
  const scoredRecent = recentDeliveries.filter((d) => d.score != null)
  const avgRecentScore = scoredRecent.length
    ? Math.round(scoredRecent.reduce((acc, d) => acc + (d.score ?? 0), 0) / scoredRecent.length)
    : null

  return (
    <div className="space-y-4">
      {toast && (
        <div className="fixed bottom-20 md:bottom-6 right-4 z-50 bg-[#18181B] text-white text-xs font-medium px-4 py-2.5 rounded-xl shadow-lg">
          {toast}
        </div>
      )}

      {/* Header + Segmented Switch: Lieferungen | Statistiken */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-[#18181B]">
            {subTab === 'stats' ? 'Einkaufs-Statistiken' : 'Vergangene Einkäufe'}
          </h2>
          <p className="text-xs text-zinc-500">
            {subTab === 'stats'
              ? 'Ausgaben nach Lebensmittel & Kategorie, Preisänderungen, Protein pro Euro & Rhythmus.'
              : 'Alle Lieferungen mit Qualitäts-Aufschlüsselung, 1-Klick Re-Add & Mealie-Wochenplan.'}
          </p>
        </div>

        <div className="inline-flex p-1 rounded-xl bg-white border border-[#E5E4DF] gap-1 shrink-0">
          <button
            type="button"
            onClick={() => switchSubTab('deliveries')}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition cursor-pointer ${
              subTab === 'deliveries'
                ? 'bg-[#18181B] text-white'
                : 'text-zinc-600 hover:bg-[#FAF9F6]'
            }`}
          >
            <Receipt className="w-3.5 h-3.5" />
            Lieferungen
          </button>
          <button
            type="button"
            onClick={() => switchSubTab('stats')}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition cursor-pointer ${
              subTab === 'stats'
                ? 'bg-[#18181B] text-white'
                : 'text-zinc-600 hover:bg-[#FAF9F6]'
            }`}
          >
            <BarChart3 className="w-3.5 h-3.5" />
            Statistiken
          </button>
        </div>
      </div>

      {subTab === 'stats' ? (
        <StatsView onAddToCart={handleReAdd} busyId={busyId} />
      ) : loading ? (
        <div className="space-y-3 animate-pulse">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-24 rounded-2xl bg-white border border-[#E5E4DF]" />
          ))}
        </div>
      ) : !deliveries.length ? (
        <div className="bg-white border border-[#E5E4DF] rounded-2xl p-8 text-center text-sm text-zinc-500">
          Noch keine vergangenen Picnic-Lieferungen vorhanden.
        </div>
      ) : (
        <>
          {/* Calm 8-Week Spend & Quality Context */}
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-white border border-[#E5E4DF] rounded-2xl p-3.5">
              <div className="text-[11px] text-zinc-400 font-medium">Ø pro Woche</div>
              <div className="mt-1 text-base sm:text-lg font-semibold text-[#18181B] tabular-nums">
                {formatEuro(avgWeeklyCents)}
              </div>
            </div>
            <div className="bg-white border border-[#E5E4DF] rounded-2xl p-3.5">
              <div className="text-[11px] text-zinc-400 font-medium">
                Gesamt ({uniqueWeeks} Wo.)
              </div>
              <div className="mt-1 text-base sm:text-lg font-semibold text-[#18181B] tabular-nums">
                {formatEuro(totalRecentCents)}
              </div>
            </div>
            <div className="bg-white border border-[#E5E4DF] rounded-2xl p-3.5">
              <div className="text-[11px] text-zinc-400 font-medium">Ø Wochen-Score</div>
              <div className="mt-1 text-base sm:text-lg font-semibold text-[#2E7D5B] tabular-nums">
                {avgRecentScore != null ? `${avgRecentScore}/100` : '—'}
              </div>
            </div>
          </div>

          {deliveries.map((d) => {
        const isOpen = expandedId === d.delivery_id
        const weekRecipes = mealieByWeek[d.iso_week] ?? []
        const scoreTone =
          (d.score ?? 0) >= 75
            ? 'bg-[#2E7D5B]/10 text-[#2E7D5B]'
            : (d.score ?? 0) >= 60
              ? 'bg-zinc-100 text-zinc-700'
              : 'bg-[#D97706]/12 text-[#B45309]'

        return (
          <article
            key={d.delivery_id}
            className="bg-white border border-[#E5E4DF] rounded-2xl overflow-hidden"
          >
            <button
              type="button"
              onClick={() => toggleExpand(d)}
              className="w-full p-4 sm:p-5 flex items-center justify-between gap-4 text-left hover:bg-[#FAF9F6]/70 transition cursor-pointer"
            >
              <div className="flex items-center gap-3.5 min-w-0">
                <div
                  className={`w-12 h-12 rounded-xl flex flex-col items-center justify-center font-semibold tabular-nums shrink-0 ${scoreTone}`}
                >
                  <span className="text-lg leading-none">{d.score ?? '—'}</span>
                  <span className="text-[9px] opacity-75 mt-0.5">SCORE</span>
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-semibold text-sm text-[#18181B]">
                      {formatShortDate(d.delivery_time)}
                    </span>
                    <span className="text-xs px-2 py-0.5 rounded-full bg-[#FAF9F6] border border-[#E5E4DF] text-zinc-500 tabular-nums">
                      {d.iso_week}
                    </span>
                  </div>
                  <div className="mt-1 flex items-center flex-wrap gap-x-3 gap-y-0.5 text-xs text-zinc-500 tabular-nums">
                    <span>{d.item_count} Artikel</span>
                    <span>{formatEuro(d.total_price_cents)}</span>
                    {d.protein_per_1000_kcal != null && (
                      <span>Protein {d.protein_per_1000_kcal.toFixed(0)} g</span>
                    )}
                    {d.fresh_share_pct != null && <span>Frisch {d.fresh_share_pct.toFixed(0)} %</span>}
                    {d.snack_share_pct != null && <span>Snacks {d.snack_share_pct.toFixed(0)} %</span>}
                  </div>
                </div>
              </div>

              {isOpen ? (
                <ChevronUp className="w-4 h-4 text-zinc-400 shrink-0" />
              ) : (
                <ChevronDown className="w-4 h-4 text-zinc-400 shrink-0" />
              )}
            </button>

            {isOpen && (
              <div className="border-t border-[#ECEBE6] p-4 sm:p-5 bg-[#FAF9F6]/50 space-y-5">
                {/* Line items with thumbnails, 1-tap ignore, and 1-click re-add */}
                <div>
                  <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-2.5">
                    <Receipt className="w-3.5 h-3.5" />
                    Artikel dieser Lieferung
                  </div>
                  <div className="bg-white border border-[#E5E4DF] rounded-xl divide-y divide-[#ECEBE6]">
                    {d.items.map((item) => (
                      <div
                        key={item.id}
                        className={`px-3.5 py-2.5 flex items-center justify-between gap-2.5 ${
                          item.ignored ? 'opacity-60' : ''
                        }`}
                      >
                        <div className="flex items-center gap-2.5 min-w-0">
                          <ProductThumb src={item.image_url} alt={item.display_name} size="sm" />
                          <div className="min-w-0">
                            <div className="text-sm font-medium text-[#18181B] truncate">
                              <span className="text-zinc-400 tabular-nums mr-1.5">
                                {item.quantity}×
                              </span>
                              {item.display_name}
                            </div>
                            <div className="mt-1 flex items-center flex-wrap gap-1.5">
                              <BucketBadge bucket={item.bucket} />
                              <NovaBadge nova={item.nova_group} />
                              {item.ignored && (
                                <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-100 text-zinc-500">
                                  Ignoriert
                                </span>
                              )}
                              <span className="text-[11px] text-zinc-400 tabular-nums">
                                {formatEuro(item.price_cents)}
                              </span>
                            </div>
                          </div>
                        </div>

                        <div className="shrink-0 flex items-center gap-1.5">
                          {item.is_food && (
                            <button
                              type="button"
                              disabled={busyId === item.picnic_id}
                              onClick={() =>
                                handleToggleIgnore(item.picnic_id, item.display_name, item.ignored)
                              }
                              title={
                                item.ignored
                                  ? 'Wieder im Score berücksichtigen'
                                  : '1-Tap ignorieren (Familie)'
                              }
                              className={`p-1.5 rounded-lg border transition cursor-pointer disabled:opacity-50 ${
                                item.ignored
                                  ? 'border-[#2E7D5B]/30 bg-[#2E7D5B]/8 text-[#2E7D5B]'
                                  : 'border-[#E5E4DF] bg-[#FAF9F6] text-zinc-400 hover:text-zinc-700'
                              }`}
                            >
                              {item.ignored ? (
                                <Eye className="w-3.5 h-3.5" />
                              ) : (
                                <EyeOff className="w-3.5 h-3.5" />
                              )}
                            </button>
                          )}

                          <button
                            type="button"
                            disabled={busyId === item.picnic_id}
                            onClick={() => handleReAdd(item.picnic_id, item.display_name)}
                            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-[#E5E4DF] bg-[#FAF9F6] hover:bg-[#2E7D5B] hover:text-white hover:border-[#2E7D5B] text-xs font-medium text-zinc-700 transition cursor-pointer disabled:opacity-50"
                          >
                            <Plus className="w-3 h-3" />1
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Associated Mealie week */}
                {weekRecipes.length > 0 && (
                  <div>
                    <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-2.5">
                      <Utensils className="w-3.5 h-3.5" />
                      Mealie-Rezepte in {d.iso_week}
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                      {weekRecipes.map((entry) => (
                        <MealieRecipeCard key={entry.id} entry={entry} />
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </article>
        )
      })}
        </>
      )}
    </div>
  )
}
