import { Eye, EyeOff, Minus, Plus, Search, ShoppingBag, Sparkles, TrendingUp, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api, formatEuro, formatShortDate, type Cart, type Product } from '../api/client'
import { BucketBadge, NovaBadge } from '../components/BucketBadge'
import { DriversCard } from '../components/DriversCard'
import { ProductThumb } from '../components/ProductThumb'
import { GoalChecklist, StreakAndBestBadges, TierPill } from '../components/QualityBadges'
import { RatioBars } from '../components/RatioBars'

type StapleFilter = 'all' | 'high_protein' | 'fresh' | 'favorites'

interface Props {
  onCartCountChange?: (count: number) => void
}

export function CartPage({ onCartCountChange }: Props) {
  const [cart, setCart] = useState<Cart | null>(null)
  const [staples, setStaples] = useState<Product[]>([])
  const [filter, setFilter] = useState<StapleFilter>('high_protein')
  const [search, setSearch] = useState('')
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [lastScoreChange, setLastScoreChange] = useState<{
    from: number
    to: number
    diff: number
  } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)

  const showToast = (msg: string) => {
    setToast(msg)
    setTimeout(() => setToast((cur) => (cur === msg ? null : cur)), 3000)
  }

  const loadCart = async () => {
    try {
      setError(null)
      const c = await api.getCart()
      setCart(c)
      onCartCountChange?.(c.item_count)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Warenkorb konnte nicht geladen werden')
    }
  }

  const loadStaples = async (f: StapleFilter, q: string) => {
    try {
      const list = await api.getStaples(f, q)
      setStaples(list)
    } catch {
      // keep existing staples on transient error
    }
  }

  useEffect(() => {
    void loadCart()
  }, [])

  useEffect(() => {
    const t = setTimeout(() => {
      void loadStaples(filter, search)
    }, 150)
    return () => clearTimeout(t)
  }, [filter, search])

  const applyCartUpdate = (updated: Cart, label?: string) => {
    const prevScore = cart?.metrics.score
    setCart(updated)
    onCartCountChange?.(updated.item_count)

    if (prevScore != null && prevScore !== updated.metrics.score) {
      const diff = updated.metrics.score - prevScore
      setLastScoreChange({ from: prevScore, to: updated.metrics.score, diff })
      setTimeout(() => setLastScoreChange(null), 4000)
      const sign = diff > 0 ? `+${diff}` : `${diff}`
      showToast(
        label
          ? `${label} · Score ${prevScore} → ${updated.metrics.score} (${sign})`
          : `Score ${prevScore} → ${updated.metrics.score} (${sign})`,
      )
    } else if (label) {
      showToast(label)
    }
  }

  const handleModify = async (productId: string, action: 'add' | 'remove', productName?: string) => {
    setBusyId(productId)
    setError(null)
    try {
      const updated =
        action === 'add' ? await api.addToCart(productId, 1) : await api.removeFromCart(productId, 1)
      applyCartUpdate(updated, action === 'add' && productName ? `${productName} (+1)` : undefined)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Aktion fehlgeschlagen')
    } finally {
      setBusyId(null)
    }
  }

  const handleToggleIgnore = async (picnicId: string, name: string, currentlyIgnored: boolean) => {
    setBusyId(picnicId)
    setError(null)
    try {
      await api.updateProduct(
        picnicId,
        currentlyIgnored
          ? { ignored: false, ignored_reason: null }
          : { ignored: true, ignored_reason: 'family' },
      )
      const refreshed = await api.getCart()
      applyCartUpdate(
        refreshed,
        currentlyIgnored ? `${name} wieder aktiv` : `${name} als Familie ignoriert`,
      )
      void loadStaples(filter, search)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Status konnte nicht geändert werden')
    } finally {
      setBusyId(null)
    }
  }

  const filterTabs: { key: StapleFilter; label: string }[] = [
    { key: 'high_protein', label: 'High Protein' },
    { key: 'fresh', label: 'Frisch' },
    { key: 'favorites', label: 'Favoriten' },
    { key: 'all', label: 'Alle' },
  ]

  const staplesPanel = (
    <div className="space-y-3.5">
      <div>
        <h3 className="text-sm font-semibold text-[#18181B]">
          Aus vergangenen Einkäufen hinzufügen
        </h3>
        <p className="text-xs text-zinc-500 mt-0.5">
          1-Klick Re-Add direkt in deinen aktiven Picnic-Warenkorb.
        </p>
      </div>

      <div className="relative">
        <Search className="w-4 h-4 text-zinc-400 absolute left-3 top-1/2 -translate-y-1/2" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Produkt suchen (z. B. Skyr, Brokkoli)…"
          className="w-full pl-9 pr-3 py-2 text-sm rounded-xl border border-[#E5E4DF] bg-[#FAF9F6] focus:bg-white focus:outline-none focus:border-[#2E7D5B]"
        />
      </div>

      <div className="flex flex-wrap gap-1.5">
        {filterTabs.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setFilter(t.key)}
            className={`px-3 py-1 rounded-full text-xs font-medium border transition cursor-pointer ${
              filter === t.key
                ? 'bg-[#18181B] text-white border-[#18181B]'
                : 'bg-[#FAF9F6] text-zinc-600 border-[#E5E4DF] hover:bg-zinc-100'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="divide-y divide-[#ECEBE6] max-h-[460px] overflow-y-auto pr-1">
        {staples.length === 0 ? (
          <p className="py-6 text-xs text-zinc-400 text-center">Keine passenden Produkte gefunden.</p>
        ) : (
          staples.map((p) => (
            <div key={p.picnic_id} className="py-2.5 flex items-center justify-between gap-2.5">
              <div className="flex items-center gap-2.5 min-w-0">
                <ProductThumb src={p.image_url} alt={p.name} size="sm" />
                <div className="min-w-0">
                  <div className="text-sm font-medium text-[#18181B] truncate">{p.name}</div>
                  <div className="mt-1 flex items-center flex-wrap gap-1.5">
                    <BucketBadge bucket={p.bucket} />
                    <NovaBadge nova={p.nova_group} />
                    {p.protein_g_per_100g != null && p.protein_g_per_100g >= 10 && (
                      <span className="text-[11px] text-[#2E7D5B] font-medium tabular-nums">
                        {p.protein_g_per_100g.toFixed(0)} g Prot.
                      </span>
                    )}
                    <span className="text-[11px] text-zinc-400 tabular-nums">
                      {p.purchase_count}×
                    </span>
                  </div>
                </div>
              </div>
              <button
                type="button"
                disabled={busyId === p.picnic_id}
                onClick={() => handleModify(p.picnic_id, 'add', p.name)}
                className="shrink-0 inline-flex items-center gap-1 px-3 py-1.5 rounded-xl bg-[#2E7D5B] hover:bg-[#25664a] text-white text-xs font-semibold transition cursor-pointer disabled:opacity-50"
              >
                <Plus className="w-3.5 h-3.5" />1
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  )

  return (
    <div className="space-y-5">
      {toast && (
        <div className="fixed bottom-20 md:bottom-6 right-4 z-50 bg-[#18181B] text-white text-xs font-medium px-4 py-2.5 rounded-xl shadow-lg tabular-nums">
          {toast}
        </div>
      )}

      {error && (
        <div className="bg-[#D97706]/10 border border-[#D97706]/30 text-[#92400E] rounded-2xl p-3.5 text-sm">
          {error}
        </div>
      )}

      {/* Pre-Checkout Score Banner */}
      <section className="bg-white border border-[#E5E4DF] rounded-2xl p-5 sm:p-6 space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-2">
            <div className="flex items-center flex-wrap gap-2 text-xs font-medium uppercase tracking-wider text-zinc-400">
              <ShoppingBag className="w-3.5 h-3.5 text-[#2E7D5B]" />
              <span>Pre-Checkout Live-Check</span>
              {cart?.next_slot_start && (
                <span>· Lieferung {formatShortDate(cart.next_slot_start)}</span>
              )}
              {cart && <TierPill tier={cart.metrics.tier} />}
            </div>

            <div className="flex items-baseline flex-wrap gap-3">
              <span className="text-5xl font-semibold tracking-tight tabular-nums">
                {cart ? cart.metrics.score : '—'}
              </span>
              <span className="text-base text-zinc-400">/100</span>
              {lastScoreChange && (
                <span
                  className={`px-2.5 py-0.5 rounded-full text-xs font-semibold tabular-nums ${
                    lastScoreChange.diff > 0
                      ? 'bg-[#2E7D5B] text-white'
                      : 'bg-[#D97706] text-white'
                  }`}
                >
                  {lastScoreChange.from} → {lastScoreChange.to} (
                  {lastScoreChange.diff > 0 ? `+${lastScoreChange.diff}` : lastScoreChange.diff})
                </span>
              )}
              {cart?.delta_vs_avg != null && (
                <span
                  className={`px-2.5 py-0.5 rounded-full text-xs font-semibold tabular-nums ${
                    cart.delta_vs_avg >= 0
                      ? 'bg-[#2E7D5B]/10 text-[#2E7D5B]'
                      : 'bg-[#D97706]/12 text-[#B45309]'
                  }`}
                >
                  {cart.delta_vs_avg >= 0 ? `+${cart.delta_vs_avg}` : cart.delta_vs_avg} vs. Schnitt
                </span>
              )}
            </div>

            {cart && <StreakAndBestBadges isPersonalBest={cart.is_personal_best} />}
          </div>

          <div className="text-right">
            <div className="text-lg font-semibold tabular-nums">
              {cart ? formatEuro(cart.total_price_cents) : '0,00 €'}
            </div>
            <div className="text-xs text-zinc-500 tabular-nums">
              {cart?.item_count ?? 0} Artikel im Warenkorb
            </div>
            <button
              type="button"
              onClick={() => setDrawerOpen(true)}
              className="mt-2.5 lg:hidden inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[#2E7D5B] text-white text-xs font-medium cursor-pointer"
            >
              <Plus className="w-3.5 h-3.5" />
              Favoriten hinzufügen
            </button>
          </div>
        </div>

        {cart && <GoalChecklist tier={cart.metrics.tier} />}

        {cart && cart.metrics.insight_text && (
          <div className="flex items-start gap-2.5 p-3.5 rounded-xl bg-[#FAF9F6] border border-[#E5E4DF] text-sm text-zinc-700">
            <Sparkles className="w-4 h-4 text-[#2E7D5B] shrink-0 mt-0.5" />
            <span>{cart.metrics.insight_text}</span>
          </div>
        )}

        {/* Deterministic Quick-Win Boosters */}
        {cart && cart.quick_wins.length > 0 && (
          <div className="space-y-2">
            <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-[#2E7D5B]">
              <TrendingUp className="w-3.5 h-3.5" />
              Quick-Wins aus deinen Favoriten
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
              {cart.quick_wins.map((qw) => (
                <div
                  key={qw.picnic_id}
                  className="flex items-center justify-between gap-2.5 p-2.5 rounded-xl bg-[#2E7D5B]/[0.05] border border-[#2E7D5B]/20"
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <ProductThumb src={qw.image_url} alt={qw.name} size="sm" />
                    <div className="min-w-0">
                      <div className="text-xs font-semibold text-[#18181B] truncate">{qw.name}</div>
                      <div className="text-[11px] text-[#2E7D5B] font-medium tabular-nums">
                        +{qw.score_delta} Pkt. → {qw.projected_score} · {qw.reason}
                      </div>
                    </div>
                  </div>
                  <button
                    type="button"
                    disabled={busyId === qw.picnic_id}
                    onClick={() => handleModify(qw.picnic_id, 'add', qw.name)}
                    className="shrink-0 inline-flex items-center gap-0.5 px-2.5 py-1.5 rounded-lg bg-[#2E7D5B] hover:bg-[#25664a] text-white text-xs font-semibold cursor-pointer disabled:opacity-50"
                  >
                    <Plus className="w-3 h-3" />1
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {cart && <RatioBars metrics={cart.metrics} />}
      </section>

      {cart && (
        <DriversCard
          positive={cart.metrics.positive_drivers}
          negative={cart.metrics.negative_drivers}
        />
      )}

      {/* Split Layout: Cart items + Desktop Re-Add Panel */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        <section className="lg:col-span-3 bg-white border border-[#E5E4DF] rounded-2xl p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-[#18181B]">Aktuelle Artikel</h2>
            <span className="text-xs text-zinc-400 tabular-nums">
              {cart?.items.length ?? 0} Positionen
            </span>
          </div>

          {!cart || cart.items.length === 0 ? (
            <p className="py-8 text-sm text-zinc-400 text-center">
              Dein Warenkorb ist aktuell leer. Füge rechts Produkte aus vergangenen Einkäufen hinzu.
            </p>
          ) : (
            <div className="divide-y divide-[#ECEBE6]">
              {cart.items.map((item) => (
                <div
                  key={item.picnic_id}
                  className={`py-3 flex items-center justify-between gap-2.5 ${
                    item.ignored ? 'opacity-60' : ''
                  }`}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <ProductThumb src={item.image_url} alt={item.name} />
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-[#18181B] truncate">
                          {item.name}
                        </span>
                        {item.ignored && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-100 text-zinc-500">
                            Ignoriert
                          </span>
                        )}
                      </div>
                      <div className="mt-1 flex items-center flex-wrap gap-1.5">
                        <BucketBadge bucket={item.bucket} />
                        <NovaBadge nova={item.nova_group} />
                        {item.unit_quantity && (
                          <span className="text-[11px] text-zinc-400">{item.unit_quantity}</span>
                        )}
                        <span className="text-[11px] text-zinc-500 tabular-nums">
                          · {formatEuro(item.price_cents)}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="shrink-0 flex items-center gap-1.5">
                    {item.is_food && (
                      <button
                        type="button"
                        disabled={busyId === item.picnic_id}
                        onClick={() => handleToggleIgnore(item.picnic_id, item.name, item.ignored)}
                        title={
                          item.ignored
                            ? 'Wieder im Score berücksichtigen'
                            : '1-Tap ignorieren (Familie / Kindersnack)'
                        }
                        className={`w-7 h-7 rounded-lg border flex items-center justify-center transition cursor-pointer disabled:opacity-50 ${
                          item.ignored
                            ? 'border-[#2E7D5B]/30 bg-[#2E7D5B]/8 text-[#2E7D5B]'
                            : 'border-[#E5E4DF] bg-[#FAF9F6] hover:bg-zinc-100 text-zinc-400 hover:text-zinc-700'
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
                      onClick={() => handleModify(item.picnic_id, 'remove')}
                      aria-label={`${item.name} entfernen`}
                      className="w-7 h-7 rounded-lg border border-[#E5E4DF] bg-[#FAF9F6] hover:bg-zinc-100 flex items-center justify-center text-zinc-700 cursor-pointer disabled:opacity-50"
                    >
                      <Minus className="w-3.5 h-3.5" />
                    </button>
                    <span className="w-6 text-center text-sm font-semibold tabular-nums">
                      {item.quantity}
                    </span>
                    <button
                      type="button"
                      disabled={busyId === item.picnic_id}
                      onClick={() => handleModify(item.picnic_id, 'add', item.name)}
                      aria-label={`${item.name} hinzufügen`}
                      className="w-7 h-7 rounded-lg border border-[#E5E4DF] bg-[#FAF9F6] hover:bg-zinc-100 flex items-center justify-center text-zinc-700 cursor-pointer disabled:opacity-50"
                    >
                      <Plus className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Desktop Re-Add Sidebar Panel */}
        <aside className="hidden lg:block lg:col-span-2 bg-white border border-[#E5E4DF] rounded-2xl p-5 h-fit sticky top-20">
          {staplesPanel}
        </aside>
      </div>

      {/* Mobile Bottom Sheet Drawer for Re-Add */}
      {drawerOpen && (
        <div className="fixed inset-0 z-50 lg:hidden flex items-end bg-black/30 backdrop-blur-[1px]">
          <div className="w-full max-h-[85vh] overflow-y-auto bg-white rounded-t-3xl p-5 border-t border-[#E5E4DF]">
            <div className="flex justify-end mb-2">
              <button
                type="button"
                onClick={() => setDrawerOpen(false)}
                className="p-1.5 rounded-lg text-zinc-500 hover:bg-zinc-100"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            {staplesPanel}
          </div>
        </div>
      )}
    </div>
  )
}
