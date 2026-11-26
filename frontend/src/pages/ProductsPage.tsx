import { Eye, EyeOff, Plus, RefreshCw, Search, SlidersHorizontal, Sparkles } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api, type BucketType, type Product } from '../api/client'
import { BUCKET_LABELS, BucketBadge, NovaBadge } from '../components/BucketBadge'
import { ProductThumb } from '../components/ProductThumb'

const BUCKET_OPTIONS: BucketType[] = [
  'produce',
  'protein',
  'whole_food',
  'staple',
  'treat_snack',
  'beverage',
  'household',
]

interface Props {
  onCartCountChange?: (count: number) => void
}

interface NutritionDraft {
  weight: string
  kcal: string
  protein: string
  sugar: string
}

export function ProductsPage({ onCartCountChange }: Props) {
  const [products, setProducts] = useState<Product[]>([])
  const [search, setSearch] = useState('')
  const [bucketFilter, setBucketFilter] = useState<string>('all')
  const [ignoredFilter, setIgnoredFilter] = useState<'all' | 'only' | 'exclude' | 'pending'>('all')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [draft, setDraft] = useState<NutritionDraft>({
    weight: '',
    kcal: '',
    protein: '',
    sugar: '',
  })
  const [busyId, setBusyId] = useState<string | null>(null)
  const [enriching, setEnriching] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const showToast = (msg: string) => {
    setToast(msg)
    setTimeout(() => setToast((cur) => (cur === msg ? null : cur)), 3000)
  }

  const openEditor = (p: Product) => {
    if (editingId === p.picnic_id) {
      setEditingId(null)
      return
    }
    setEditingId(p.picnic_id)
    setDraft({
      weight: p.parsed_weight_g != null ? String(Math.round(p.parsed_weight_g)) : '',
      kcal: p.kcal_per_100g != null ? String(Math.round(p.kcal_per_100g)) : '',
      protein: p.protein_g_per_100g != null ? String(p.protein_g_per_100g) : '',
      sugar: p.sugar_g_per_100g != null ? String(p.sugar_g_per_100g) : '',
    })
  }

  const load = async () => {
    try {
      const list = await api.getProducts({
        q: search,
        bucket: bucketFilter,
        ignored: ignoredFilter,
      })
      setProducts(list)
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Produkte konnten nicht geladen werden')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    const t = setTimeout(() => {
      void load()
    }, 140)
    return () => clearTimeout(t)
  }, [search, bucketFilter, ignoredFilter])

  const patchProduct = async (
    picnicId: string,
    patch: {
      ignored?: boolean
      ignored_reason?: string | null
      bucket?: BucketType
      nova_group?: number
      parsed_weight_g?: number
      kcal_per_100g?: number
      protein_g_per_100g?: number
      sugar_g_per_100g?: number
    },
    successMsg?: string,
  ) => {
    setBusyId(picnicId)
    try {
      const updated = await api.updateProduct(picnicId, patch)
      setProducts((prev) => prev.map((p) => (p.picnic_id === picnicId ? updated : p)))
      if (successMsg) showToast(successMsg)
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Änderung fehlgeschlagen')
    } finally {
      setBusyId(null)
    }
  }

  const handleSaveNutrition = async (picnicId: string) => {
    const patch: {
      parsed_weight_g?: number
      kcal_per_100g?: number
      protein_g_per_100g?: number
      sugar_g_per_100g?: number
    } = {}
    const w = Number(draft.weight)
    if (draft.weight.trim() !== '' && Number.isFinite(w) && w > 0) patch.parsed_weight_g = w
    const kc = Number(draft.kcal)
    if (draft.kcal.trim() !== '' && Number.isFinite(kc) && kc >= 0) patch.kcal_per_100g = kc
    const pr = Number(draft.protein)
    if (draft.protein.trim() !== '' && Number.isFinite(pr) && pr >= 0) patch.protein_g_per_100g = pr
    const su = Number(draft.sugar)
    if (draft.sugar.trim() !== '' && Number.isFinite(su) && su >= 0) patch.sugar_g_per_100g = su

    await patchProduct(picnicId, patch, 'Nährwerte & Gewicht gespeichert')
  }

  const handleReEnrichSingle = async (picnicId: string, name: string) => {
    setBusyId(picnicId)
    try {
      const updated = await api.reEnrichProduct(picnicId)
      setProducts((prev) => prev.map((p) => (p.picnic_id === picnicId ? updated : p)))
      setDraft({
        weight: updated.parsed_weight_g != null ? String(Math.round(updated.parsed_weight_g)) : '',
        kcal: updated.kcal_per_100g != null ? String(Math.round(updated.kcal_per_100g)) : '',
        protein: updated.protein_g_per_100g != null ? String(updated.protein_g_per_100g) : '',
        sugar: updated.sugar_g_per_100g != null ? String(updated.sugar_g_per_100g) : '',
      })
      showToast(`${name}: neu angereichert (${updated.enrichment_source})`)
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Neu-Anreicherung fehlgeschlagen')
    } finally {
      setBusyId(null)
    }
  }

  const handleAddToCart = async (picnicId: string, name: string) => {
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

  const handleEnrichPending = async () => {
    setEnriching(true)
    try {
      const res = await api.enrichProductsNow()
      showToast(
        `Anreicherung fertig: ${res.openfoodfacts} OFF, ${res.llm} LLM, ${res.rule_non_food} Haushalt`,
      )
      await load()
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Anreicherung fehlgeschlagen')
    } finally {
      setEnriching(false)
    }
  }

  const pendingCount = products.filter((p) => p.enrichment_source === 'pending').length

  return (
    <div className="space-y-4">
      {toast && (
        <div className="fixed bottom-20 md:bottom-6 right-4 z-50 bg-[#18181B] text-white text-xs font-medium px-4 py-2.5 rounded-xl shadow-lg">
          {toast}
        </div>
      )}

      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-[#18181B]">Produktkatalog & Regeln</h2>
          <p className="text-xs text-zinc-500">
            Jedes Picnic-Produkt wird einmalig angereichert. Manuelle Änderungen haben immer Vorrang.
          </p>
        </div>
        <span className="text-xs text-zinc-400 tabular-nums">{products.length} Produkte</span>
      </div>

      {/* Pending Enrichment Banner */}
      {pendingCount > 0 && (
        <div className="bg-[#2E7D5B]/8 border border-[#2E7D5B]/25 rounded-2xl p-3.5 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-xs text-[#1F5A41]">
            <Sparkles className="w-4 h-4 shrink-0" />
            <span>
              <strong>{pendingCount}</strong> Produkte warten auf Nährwert-Anreicherung
              (OpenFoodFacts / DeepSeek Flash).
            </span>
          </div>
          <button
            type="button"
            disabled={enriching}
            onClick={handleEnrichPending}
            className="px-3 py-1.5 rounded-xl bg-[#2E7D5B] hover:bg-[#25664a] text-white text-xs font-medium cursor-pointer disabled:opacity-50"
          >
            {enriching ? 'Reichert an…' : 'Jetzt anreichern'}
          </button>
        </div>
      )}

      {/* Filter Bar */}
      <div className="bg-white border border-[#E5E4DF] rounded-2xl p-4 space-y-3">
        <div className="flex flex-col sm:flex-row gap-2.5">
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-zinc-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Nach Produktname oder Kategorie suchen…"
              className="w-full pl-9 pr-3 py-2 text-sm rounded-xl border border-[#E5E4DF] bg-[#FAF9F6] focus:bg-white focus:outline-none focus:border-[#2E7D5B]"
            />
          </div>

          <select
            value={ignoredFilter}
            onChange={(e) =>
              setIgnoredFilter(e.target.value as 'all' | 'only' | 'exclude' | 'pending')
            }
            className="px-3 py-2 text-sm rounded-xl border border-[#E5E4DF] bg-[#FAF9F6] text-zinc-700 focus:outline-none"
          >
            <option value="all">Alle anzeigen</option>
            <option value="exclude">Nur aktive Lebensmittel</option>
            <option value="only">Nur ignorierte Artikel</option>
            <option value="pending">Nur unangereichert (pending)</option>
          </select>
        </div>

        <div className="flex flex-wrap gap-1.5">
          <button
            type="button"
            onClick={() => setBucketFilter('all')}
            className={`px-3 py-1 rounded-full text-xs font-medium border transition cursor-pointer ${
              bucketFilter === 'all'
                ? 'bg-[#18181B] text-white border-[#18181B]'
                : 'bg-[#FAF9F6] text-zinc-600 border-[#E5E4DF] hover:bg-zinc-100'
            }`}
          >
            Alle Buckets
          </button>
          {BUCKET_OPTIONS.map((b) => (
            <button
              key={b}
              type="button"
              onClick={() => setBucketFilter(b)}
              className={`px-3 py-1 rounded-full text-xs font-medium border transition cursor-pointer ${
                bucketFilter === b
                  ? 'bg-[#18181B] text-white border-[#18181B]'
                  : 'bg-[#FAF9F6] text-zinc-600 border-[#E5E4DF] hover:bg-zinc-100'
              }`}
            >
              {BUCKET_LABELS[b]}
            </button>
          ))}
        </div>
      </div>

      {/* Product List */}
      <div className="bg-white border border-[#E5E4DF] rounded-2xl divide-y divide-[#ECEBE6]">
        {loading ? (
          <div className="p-6 text-sm text-zinc-400">Lade Produkte…</div>
        ) : products.length === 0 ? (
          <div className="p-8 text-sm text-zinc-400 text-center">Keine Produkte gefunden.</div>
        ) : (
          products.map((p) => {
            const isEditing = editingId === p.picnic_id
            return (
              <div key={p.picnic_id} className="p-4 space-y-2.5">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className={`flex items-center gap-3 min-w-0 ${p.ignored ? 'opacity-60' : ''}`}>
                    <ProductThumb src={p.image_url} alt={p.name} />
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-semibold text-[#18181B]">{p.name}</span>
                        {p.unit_quantity && (
                          <span className="text-xs text-zinc-400">{p.unit_quantity}</span>
                        )}
                        {p.manual_override && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#2E7D5B]/10 text-[#2E7D5B] font-medium">
                            Manuell
                          </span>
                        )}
                      </div>

                      <div className="mt-1.5 flex items-center flex-wrap gap-1.5 text-xs text-zinc-500">
                        <BucketBadge bucket={p.bucket} />
                        <NovaBadge nova={p.nova_group} />
                        {p.kcal_per_100g != null && (
                          <span className="tabular-nums">
                            {Math.round(p.kcal_per_100g)} kcal ·{' '}
                            {p.protein_g_per_100g?.toFixed(1) ?? '0'} g Prot. ·{' '}
                            {p.sugar_g_per_100g?.toFixed(1) ?? '0'} g Zucker
                          </span>
                        )}
                        <span className="text-zinc-400">· {p.enrichment_source}</span>
                        {p.ignored && (
                          <span className="text-[#B45309] font-medium">
                            · Ignoriert ({p.ignored_reason === 'family' ? 'Familie' : 'Haushalt'})
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Quick Cart Add + 1-Tap Ignore + Override Actions */}
                  <div className="shrink-0 flex items-center gap-1.5 flex-wrap">
                    <button
                      type="button"
                      disabled={busyId === p.picnic_id}
                      onClick={() => handleAddToCart(p.picnic_id, p.name)}
                      title="In Picnic-Warenkorb legen"
                      className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-xl border border-[#2E7D5B]/30 bg-[#2E7D5B]/8 hover:bg-[#2E7D5B] text-[#2E7D5B] hover:text-white text-xs font-semibold transition cursor-pointer disabled:opacity-50"
                    >
                      <Plus className="w-3.5 h-3.5" />1
                    </button>

                    {p.ignored ? (
                      <button
                        type="button"
                        disabled={busyId === p.picnic_id}
                        onClick={() =>
                          patchProduct(p.picnic_id, { ignored: false, ignored_reason: null })
                        }
                        className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-xl border border-[#E5E4DF] bg-[#FAF9F6] text-zinc-700 text-xs font-medium cursor-pointer"
                      >
                        <Eye className="w-3.5 h-3.5" />
                        Aktivieren
                      </button>
                    ) : (
                      <>
                        <button
                          type="button"
                          disabled={busyId === p.picnic_id}
                          onClick={() =>
                            patchProduct(p.picnic_id, { ignored: true, ignored_reason: 'family' })
                          }
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-xl border border-[#E5E4DF] bg-[#FAF9F6] hover:bg-zinc-100 text-zinc-700 text-xs font-medium cursor-pointer"
                        >
                          <EyeOff className="w-3.5 h-3.5" />
                          Familie
                        </button>
                        <button
                          type="button"
                          disabled={busyId === p.picnic_id}
                          onClick={() =>
                            patchProduct(p.picnic_id, {
                              ignored: true,
                              ignored_reason: 'household',
                              bucket: 'household',
                            })
                          }
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-xl border border-[#E5E4DF] bg-[#FAF9F6] hover:bg-zinc-100 text-zinc-700 text-xs font-medium cursor-pointer"
                        >
                          Haushalt
                        </button>
                      </>
                    )}

                    <button
                      type="button"
                      onClick={() => openEditor(p)}
                      className={`p-1.5 rounded-xl border transition cursor-pointer ${
                        isEditing
                          ? 'bg-[#18181B] text-white border-[#18181B]'
                          : 'border-[#E5E4DF] bg-[#FAF9F6] text-zinc-600 hover:bg-zinc-100'
                      }`}
                      title="Bucket, NOVA & Nährwerte anpassen"
                    >
                      <SlidersHorizontal className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                {/* Inline Bucket, NOVA, Weight & Macro Override Controls */}
                {isEditing && (
                  <div className="pt-3 border-t border-[#ECEBE6] space-y-3 text-xs">
                    <div className="flex flex-wrap items-center justify-between gap-2.5">
                      <div className="flex flex-wrap items-center gap-3">
                        <label className="flex items-center gap-2 text-zinc-600">
                          Bucket:
                          <select
                            value={p.bucket}
                            onChange={(e) =>
                              patchProduct(p.picnic_id, { bucket: e.target.value as BucketType })
                            }
                            className="px-2.5 py-1.5 rounded-lg border border-[#E5E4DF] bg-[#FAF9F6] text-[#18181B]"
                          >
                            {BUCKET_OPTIONS.map((b) => (
                              <option key={b} value={b}>
                                {BUCKET_LABELS[b]}
                              </option>
                            ))}
                          </select>
                        </label>

                        <label className="flex items-center gap-2 text-zinc-600">
                          NOVA:
                          <select
                            value={p.nova_group ?? 2}
                            onChange={(e) =>
                              patchProduct(p.picnic_id, { nova_group: Number(e.target.value) })
                            }
                            className="px-2.5 py-1.5 rounded-lg border border-[#E5E4DF] bg-[#FAF9F6] text-[#18181B]"
                          >
                            <option value={1}>NOVA 1 (Unverarbeitet)</option>
                            <option value={2}>NOVA 2 (Küchenzutaten)</option>
                            <option value={3}>NOVA 3 (Verarbeitet)</option>
                            <option value={4}>NOVA 4 (Hochverarbeitet)</option>
                          </select>
                        </label>
                      </div>

                      <button
                        type="button"
                        disabled={busyId === p.picnic_id}
                        onClick={() => handleReEnrichSingle(p.picnic_id, p.name)}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-[#E5E4DF] bg-[#FAF9F6] hover:bg-zinc-100 text-zinc-700 font-medium cursor-pointer disabled:opacity-50"
                      >
                        <RefreshCw
                          className={`w-3 h-3 ${busyId === p.picnic_id ? 'animate-spin' : ''}`}
                        />
                        Neu anreichern
                      </button>
                    </div>

                    <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 items-end">
                      <label className="space-y-1 text-[11px] text-zinc-500">
                        <span>Gewicht (g)</span>
                        <input
                          type="number"
                          min={1}
                          max={50000}
                          step={1}
                          value={draft.weight}
                          onChange={(e) =>
                            setDraft((prev) => ({ ...prev, weight: e.target.value }))
                          }
                          placeholder="z. B. 500"
                          className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-[#E5E4DF] bg-[#FAF9F6] text-[#18181B] tabular-nums"
                        />
                      </label>
                      <label className="space-y-1 text-[11px] text-zinc-500">
                        <span>kcal / 100g</span>
                        <input
                          type="number"
                          min={0}
                          max={1000}
                          step={1}
                          value={draft.kcal}
                          onChange={(e) => setDraft((prev) => ({ ...prev, kcal: e.target.value }))}
                          placeholder="0"
                          className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-[#E5E4DF] bg-[#FAF9F6] text-[#18181B] tabular-nums"
                        />
                      </label>
                      <label className="space-y-1 text-[11px] text-zinc-500">
                        <span>Protein g / 100g</span>
                        <input
                          type="number"
                          min={0}
                          max={100}
                          step={0.1}
                          value={draft.protein}
                          onChange={(e) =>
                            setDraft((prev) => ({ ...prev, protein: e.target.value }))
                          }
                          placeholder="0"
                          className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-[#E5E4DF] bg-[#FAF9F6] text-[#18181B] tabular-nums"
                        />
                      </label>
                      <label className="space-y-1 text-[11px] text-zinc-500">
                        <span>Zucker g / 100g</span>
                        <input
                          type="number"
                          min={0}
                          max={100}
                          step={0.1}
                          value={draft.sugar}
                          onChange={(e) => setDraft((prev) => ({ ...prev, sugar: e.target.value }))}
                          placeholder="0"
                          className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-[#E5E4DF] bg-[#FAF9F6] text-[#18181B] tabular-nums"
                        />
                      </label>
                      <button
                        type="button"
                        disabled={busyId === p.picnic_id}
                        onClick={() => handleSaveNutrition(p.picnic_id)}
                        className="col-span-2 sm:col-span-1 px-3 py-1.5 rounded-lg bg-[#18181B] hover:bg-zinc-800 text-white text-xs font-medium cursor-pointer disabled:opacity-50"
                      >
                        Werte speichern
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
