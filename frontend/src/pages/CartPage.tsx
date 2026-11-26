import {
  ChevronDown,
  ChevronUp,
  Eye,
  EyeOff,
  Minus,
  Plus,
  RefreshCw,
  RotateCcw,
  Search,
  ShoppingBag,
  Sparkles,
  TrendingUp,
  Utensils,
  X,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import {
  api,
  formatEuro,
  formatShortDate,
  type Cart,
  type MealiePlanEntry,
  type PicnicSearchItem,
  type Product,
} from '../api/client'
import { BucketBadge, NovaBadge } from '../components/BucketBadge'
import { DriversCard } from '../components/DriversCard'
import { ProductThumb } from '../components/ProductThumb'
import { GoalChecklist, StreakAndBestBadges, TierPill } from '../components/QualityBadges'
import { RatioBars } from '../components/RatioBars'

type StapleFilter = 'all' | 'high_protein' | 'fresh' | 'favorites'
type AddTab = 'staples' | 'picnic_search'

interface ToastState {
  id: number
  text: string
  undo?: () => Promise<void>
}

interface Props {
  onCartCountChange?: (count: number) => void
}

function getCurrentIsoWeek(): string {
  const d = new Date()
  const utc = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()))
  const day = utc.getUTCDay() || 7
  utc.setUTCDate(utc.getUTCDate() + 4 - day)
  const yearStart = new Date(Date.UTC(utc.getUTCFullYear(), 0, 1))
  const weekNo = Math.ceil(((utc.getTime() - yearStart.getTime()) / 86400000 + 1) / 7)
  return `${utc.getUTCFullYear()}-W${String(weekNo).padStart(2, '0')}`
}

function formatRelativeAge(iso: string | null): string {
  if (!iso) return ''
  const diffSec = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000))
  if (diffSec < 60) return 'gerade eben'
  const mins = Math.floor(diffSec / 60)
  if (mins < 60) return `vor ${mins} Min.`
  const hrs = Math.floor(mins / 60)
  return `vor ${hrs} Std.`
}

export function CartPage({ onCartCountChange }: Props) {
  const [cart, setCart] = useState<Cart | null>(null)
  const [mealieEntries, setMealieEntries] = useState<MealiePlanEntry[]>([])
  const [mealieOpen, setMealieOpen] = useState(false)
  const [addTab, setAddTab] = useState<AddTab>('staples')
  const [staples, setStaples] = useState<Product[]>([])
  const [filter, setFilter] = useState<StapleFilter>('high_protein')
  const [search, setSearch] = useState('')
  const [picnicQuery, setPicnicQuery] = useState('')
  const [picnicResults, setPicnicResults] = useState<PicnicSearchItem[]>([])
  const [searchingPicnic, setSearchingPicnic] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [mobileDetailsOpen, setMobileDetailsOpen] = useState(false)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [lastScoreChange, setLastScoreChange] = useState<{
    from: number
    to: number
    diff: number
  } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<ToastState | null>(null)
  const lastAutoRefreshRef = useRef<number>(Date.now())

  const showToast = (text: string, undo?: () => Promise<void>) => {
    const id = Date.now()
    setToast({ id, text, undo })
    setTimeout(() => setToast((cur) => (cur?.id === id ? null : cur)), 4200)
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

  const handleRefreshCart = async (silent = false) => {
    setRefreshing(true)
    if (!silent) setError(null)
    try {
      const updated = await api.refreshCart()
      setCart(updated)
      onCartCountChange?.(updated.item_count)
      lastAutoRefreshRef.current = Date.now()
      if (!silent) showToast('Warenkorb aktualisiert')
    } catch (err) {
      if (!silent) {
        setError(err instanceof Error ? err.message : 'Warenkorb konnte nicht aktualisiert werden')
      }
    } finally {
      setRefreshing(false)
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
    api
      .getMealieWeek(getCurrentIsoWeek())
      .then((entries) => setMealieEntries(entries))
      .catch(() => {})
  }, [])

  // Zero-click Auto-Refresh when returning from the Picnic app (throttled to 30s)
  useEffect(() => {
    const onVisChange = () => {
      if (document.visibilityState === 'visible' && Date.now() - lastAutoRefreshRef.current > 30000) {
        void handleRefreshCart(true)
      }
    }
    document.addEventListener('visibilitychange', onVisChange)
    return () => document.removeEventListener('visibilitychange', onVisChange)
  }, [])

  useEffect(() => {
    const t = setTimeout(() => {
      void loadStaples(filter, search)
    }, 150)
    return () => clearTimeout(t)
  }, [filter, search])

  useEffect(() => {
    if (addTab !== 'picnic_search') return
    const q = picnicQuery.trim()
    if (q.length < 2) {
      setPicnicResults([])
      return
    }
    const t = setTimeout(async () => {
      setSearchingPicnic(true)
      try {
        const res = await api.searchPicnic(q)
        setPicnicResults(res)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Picnic-Suche fehlgeschlagen')
      } finally {
        setSearchingPicnic(false)
      }
    }, 260)
    return () => clearTimeout(t)
  }, [addTab, picnicQuery])

  const applyCartUpdate = (updated: Cart, label?: string, undo?: () => Promise<void>) => {
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
        undo,
      )
    } else if (label) {
      showToast(label, undo)
    }
  }

  const handleModify = async (
    productId: string,
    action: 'add' | 'remove',
    productName?: string,
    allowUndo = true,
  ) => {
    setBusyId(productId)
    setError(null)
    try {
      const updated =
        action === 'add' ? await api.addToCart(productId, 1) : await api.removeFromCart(productId, 1)
      const undo = allowUndo
        ? async () => {
            await handleModify(productId, action === 'add' ? 'remove' : 'add', productName, false)
          }
        : undefined
      applyCartUpdate(
        updated,
        productName ? `${productName} (${action === 'add' ? '+1' : '-1'})` : undefined,
        undo,
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Aktion fehlgeschlagen')
    } finally {
      setBusyId(null)
    }
  }

  const handleToggleIgnore = async (
    picnicId: string,
    name: string,
    currentlyIgnored: boolean,
    allowUndo = true,
  ) => {
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
      const undo = allowUndo
        ? async () => {
            await handleToggleIgnore(picnicId, name, !currentlyIgnored, false)
          }
        : undefined
      applyCartUpdate(
        refreshed,
        currentlyIgnored ? `${name} wieder aktiv` : `${name} ignoriert`,
        undo,
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

  const renderAddPanel = (inDrawer: boolean) => (
    <div className="space-y-3.5">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-[#18181B]">Artikel hinzufügen</h3>
        <div className="inline-flex p-0.5 rounded-xl bg-[#FAF9F6] border border-[#E5E4DF] text-xs">
          <button
            type="button"
            onClick={() => setAddTab('staples')}
            className={`px-2.5 py-1.5 rounded-lg font-medium transition cursor-pointer ${
              addTab === 'staples' ? 'bg-[#18181B] text-white' : 'text-zinc-600'
            }`}
          >
            Vergangene
          </button>
          <button
            type="button"
            onClick={() => setAddTab('picnic_search')}
            className={`px-2.5 py-1.5 rounded-lg font-medium transition cursor-pointer ${
              addTab === 'picnic_search' ? 'bg-[#18181B] text-white' : 'text-zinc-600'
            }`}
          >
            Picnic-Suche
          </button>
        </div>
      </div>

      {addTab === 'staples' ? (
        <>
          <div className="relative">
            <Search className="w-4 h-4 text-zinc-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Vergangene Produkte filtern…"
              className="w-full pl-9 pr-3 py-2.5 text-sm rounded-xl border border-[#E5E4DF] bg-[#FAF9F6] focus:bg-white focus:outline-none focus:border-[#2E7D5B]"
            />
          </div>

          <div className="flex flex-wrap gap-1.5">
            {filterTabs.map((t) => (
              <button
                key={t.key}
                type="button"
                onClick={() => setFilter(t.key)}
                className={`px-3 py-1.5 rounded-full text-xs font-medium border transition cursor-pointer ${
                  filter === t.key
                    ? 'bg-[#18181B] text-white border-[#18181B]'
                    : 'bg-[#FAF9F6] text-zinc-600 border-[#E5E4DF] hover:bg-zinc-100'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          <div
            className={`divide-y divide-[#ECEBE6] ${
              inDrawer ? '' : 'max-h-[480px] overflow-y-auto pr-1'
            }`}
          >
            {staples.length === 0 ? (
              <p className="py-6 text-xs text-zinc-400 text-center">
                Keine passenden Produkte gefunden.
              </p>
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
                      </div>
                    </div>
                  </div>
                  <button
                    type="button"
                    disabled={busyId === p.picnic_id}
                    onClick={() => handleModify(p.picnic_id, 'add', p.name)}
                    className="shrink-0 inline-flex items-center gap-1 px-3.5 py-2 rounded-xl bg-[#2E7D5B] hover:bg-[#25664a] text-white text-xs font-semibold transition cursor-pointer disabled:opacity-50"
                  >
                    <Plus className="w-3.5 h-3.5" />1
                  </button>
                </div>
              ))
            )}
          </div>
        </>
      ) : (
        <>
          <div className="relative">
            <Search className="w-4 h-4 text-zinc-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={picnicQuery}
              onChange={(e) => setPicnicQuery(e.target.value)}
              placeholder="Im Picnic-Sortiment suchen (z. B. Skyr, Lachs)…"
              className="w-full pl-9 pr-3 py-2.5 text-sm rounded-xl border border-[#E5E4DF] bg-[#FAF9F6] focus:bg-white focus:outline-none focus:border-[#2E7D5B]"
            />
          </div>

          <div
            className={`divide-y divide-[#ECEBE6] ${
              inDrawer ? '' : 'max-h-[480px] overflow-y-auto pr-1'
            }`}
          >
            {searchingPicnic ? (
              <p className="py-6 text-xs text-zinc-400 text-center">Suche bei Picnic…</p>
            ) : picnicQuery.trim().length < 2 ? (
              <p className="py-6 text-xs text-zinc-400 text-center">
                Gib mindestens 2 Buchstaben ein, um direkt im Picnic-Sortiment zu suchen.
              </p>
            ) : picnicResults.length === 0 ? (
              <p className="py-6 text-xs text-zinc-400 text-center">
                Keine Picnic-Treffer für „{picnicQuery}“.
              </p>
            ) : (
              picnicResults.map((item) => (
                <div
                  key={item.picnic_id}
                  className="py-2.5 flex items-center justify-between gap-2.5"
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <ProductThumb src={item.image_url} alt={item.name} size="sm" />
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-[#18181B] truncate">{item.name}</div>
                      <div className="mt-1 flex items-center flex-wrap gap-1.5 text-[11px] text-zinc-500">
                        {item.bucket && <BucketBadge bucket={item.bucket} />}
                        {item.nova_group && <NovaBadge nova={item.nova_group} />}
                        {item.unit_quantity && <span>{item.unit_quantity}</span>}
                        {item.price_cents > 0 && (
                          <span className="tabular-nums font-medium text-zinc-600">
                            · {formatEuro(item.price_cents)}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  <button
                    type="button"
                    disabled={busyId === item.picnic_id}
                    onClick={() => handleModify(item.picnic_id, 'add', item.name)}
                    className="shrink-0 inline-flex items-center gap-1 px-3.5 py-2 rounded-xl bg-[#2E7D5B] hover:bg-[#25664a] text-white text-xs font-semibold transition cursor-pointer disabled:opacity-50"
                  >
                    <Plus className="w-3.5 h-3.5" />1
                  </button>
                </div>
              ))
            )}
          </div>
        </>
      )}
    </div>
  )

  return (
    <div className="space-y-4">
      {/* Toast with 1-Tap Undo */}
      {toast && (
        <div className="fixed bottom-20 md:bottom-6 inset-x-4 md:inset-x-auto md:right-6 z-50 flex justify-center md:justify-end pointer-events-none">
          <div className="pointer-events-auto bg-[#18181B] text-white text-xs font-medium pl-4 pr-2.5 py-2.5 rounded-xl shadow-lg flex items-center gap-3 tabular-nums">
            <span>{toast.text}</span>
            {toast.undo && (
              <button
                type="button"
                onClick={() => {
                  const fn = toast.undo
                  setToast(null)
                  void fn?.()
                }}
                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-white/15 hover:bg-white/25 text-white font-semibold cursor-pointer"
              >
                <RotateCcw className="w-3 h-3" />
                Rückgängig
              </button>
            )}
          </div>
        </div>
      )}

      {/* Sticky Mobile Mini-Bar (keeps live score & +Artikel always within thumb reach while scrolling) */}
      {cart && (
        <div className="md:hidden sticky top-14 z-20 -mx-3.5 px-3.5 py-2 bg-[#F8F7F4]/95 backdrop-blur-md border-b border-[#E5E4DF] flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <span className="px-2.5 py-1 rounded-lg bg-[#18181B] text-white text-xs font-bold tabular-nums">
              {cart.metrics.score}/100
            </span>
            <span className="text-xs text-zinc-600 tabular-nums truncate">
              {cart.item_count} Art. · {formatEuro(cart.total_price_cents)}
            </span>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            <button
              type="button"
              disabled={refreshing}
              onClick={() => handleRefreshCart(false)}
              aria-label="Warenkorb aktualisieren"
              className="w-9 h-9 rounded-xl border border-[#E5E4DF] bg-white flex items-center justify-center text-zinc-700 cursor-pointer disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
            </button>
            <button
              type="button"
              onClick={() => setDrawerOpen(true)}
              className="h-9 px-3 rounded-xl bg-[#2E7D5B] text-white text-xs font-semibold inline-flex items-center gap-1 cursor-pointer"
            >
              <Plus className="w-3.5 h-3.5" />
              Artikel
            </button>
          </div>
        </div>
      )}

      {error && (
        <div className="bg-[#D97706]/10 border border-[#D97706]/30 text-[#92400E] rounded-2xl p-3.5 text-sm">
          {error}
        </div>
      )}

      {/* Pre-Checkout Score Banner */}
      <section className="bg-white border border-[#E5E4DF] rounded-2xl p-4 sm:p-6 space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-2">
            <div className="flex items-center flex-wrap gap-2 text-xs font-medium uppercase tracking-wider text-zinc-400">
              <ShoppingBag className="w-3.5 h-3.5 text-[#2E7D5B]" />
              <span>Pre-Checkout</span>
              {cart?.next_slot_start && (
                <span>· {formatShortDate(cart.next_slot_start)}</span>
              )}
              {cart && <TierPill tier={cart.metrics.tier} />}
            </div>

            <div className="flex items-baseline flex-wrap gap-2.5">
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

          <div className="flex flex-col items-end gap-1.5">
            <div className="text-lg font-semibold tabular-nums">
              {cart ? formatEuro(cart.total_price_cents) : '0,00 €'}
            </div>
            <div className="text-xs text-zinc-500 tabular-nums">
              {cart?.item_count ?? 0} Artikel
              {cart?.fetched_at && (
                <span className="text-zinc-400"> · {formatRelativeAge(cart.fetched_at)}</span>
              )}
            </div>
            <button
              type="button"
              disabled={refreshing}
              onClick={() => handleRefreshCart(false)}
              className="hidden md:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-[#E5E4DF] bg-[#FAF9F6] hover:bg-zinc-100 text-xs font-medium text-zinc-700 cursor-pointer disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
              {refreshing ? 'Aktualisiert…' : 'Warenkorb laden'}
            </button>
          </div>
        </div>

        {cart && <GoalChecklist tier={cart.metrics.tier} />}

        {cart && cart.metrics.insight_text && (
          <div className="flex items-start gap-2.5 p-3 rounded-xl bg-[#FAF9F6] border border-[#E5E4DF] text-sm text-zinc-700">
            <Sparkles className="w-4 h-4 text-[#2E7D5B] shrink-0 mt-0.5" />
            <span>{cart.metrics.insight_text}</span>
          </div>
        )}

        {/* Deterministic Quick-Win Boosters (Add + Remove/Ignore Detractors) */}
        {cart && (cart.quick_wins.length > 0 || cart.remove_wins.length > 0) && (
          <div className="space-y-2">
            <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-[#2E7D5B]">
              <TrendingUp className="w-3.5 h-3.5" />
              Score-Quick-Wins
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
              {cart.quick_wins.map((qw) => (
                <div
                  key={`add-${qw.picnic_id}`}
                  className="flex items-center justify-between gap-2.5 p-2.5 rounded-xl bg-[#2E7D5B]/[0.05] border border-[#2E7D5B]/20"
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <ProductThumb src={qw.image_url} alt={qw.name} size="sm" />
                    <div className="min-w-0">
                      <div className="text-xs font-semibold text-[#18181B] truncate">{qw.name}</div>
                      <div className="text-[11px] text-[#2E7D5B] font-medium tabular-nums">
                        +1 → +{qw.score_delta} Pkt. ({qw.projected_score})
                      </div>
                    </div>
                  </div>
                  <button
                    type="button"
                    disabled={busyId === qw.picnic_id}
                    onClick={() => handleModify(qw.picnic_id, 'add', qw.name)}
                    className="shrink-0 h-9 px-3 rounded-lg bg-[#2E7D5B] hover:bg-[#25664a] text-white text-xs font-semibold inline-flex items-center gap-0.5 cursor-pointer disabled:opacity-50"
                  >
                    <Plus className="w-3.5 h-3.5" />1
                  </button>
                </div>
              ))}

              {cart.remove_wins.map((rw) => (
                <div
                  key={`rem-${rw.picnic_id}`}
                  className="flex items-center justify-between gap-2.5 p-2.5 rounded-xl bg-[#D97706]/[0.06] border border-[#D97706]/25"
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <ProductThumb src={rw.image_url} alt={rw.name} size="sm" />
                    <div className="min-w-0">
                      <div className="text-xs font-semibold text-[#18181B] truncate">{rw.name}</div>
                      <div className="text-[11px] text-[#B45309] font-medium tabular-nums">
                        -1 → +{rw.score_delta} Pkt. ({rw.projected_score})
                      </div>
                    </div>
                  </div>
                  <div className="shrink-0 flex items-center gap-1.5">
                    <button
                      type="button"
                      disabled={busyId === rw.picnic_id}
                      onClick={() => handleToggleIgnore(rw.picnic_id, rw.name, false)}
                      title="Als Familie ignorieren"
                      className="w-9 h-9 rounded-lg border border-[#D97706]/30 bg-white text-[#B45309] hover:bg-[#D97706]/10 flex items-center justify-center cursor-pointer disabled:opacity-50"
                    >
                      <EyeOff className="w-3.5 h-3.5" />
                    </button>
                    <button
                      type="button"
                      disabled={busyId === rw.picnic_id}
                      onClick={() => handleModify(rw.picnic_id, 'remove', rw.name)}
                      className="h-9 px-2.5 rounded-lg bg-[#B45309] hover:bg-[#92400E] text-white text-xs font-semibold inline-flex items-center gap-0.5 cursor-pointer disabled:opacity-50"
                    >
                      <Minus className="w-3.5 h-3.5" />1
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Mobile Toggle for Ratio Details (always open on md+ Foldables & Desktop) */}
        {cart && (
          <>
            <button
              type="button"
              onClick={() => setMobileDetailsOpen((v) => !v)}
              className="md:hidden w-full py-2 rounded-xl border border-[#E5E4DF] bg-[#FAF9F6] text-xs font-medium text-zinc-600 flex items-center justify-center gap-1.5 cursor-pointer"
            >
              {mobileDetailsOpen ? (
                <>
                  Details ausblenden <ChevronUp className="w-3.5 h-3.5" />
                </>
              ) : (
                <>
                  4 Quoten & Treiber anzeigen <ChevronDown className="w-3.5 h-3.5" />
                </>
              )}
            </button>
            <div className={`${mobileDetailsOpen ? 'block' : 'hidden'} md:block space-y-4`}>
              <RatioBars metrics={cart.metrics} />
            </div>
          </>
        )}
      </section>

      {cart && (
        <div className={`${mobileDetailsOpen ? 'block' : 'hidden'} md:block`}>
          <DriversCard
            positive={cart.metrics.positive_drivers}
            negative={cart.metrics.negative_drivers}
          />
        </div>
      )}

      {/* Horizontal 1-Tap Favoriten Quick-Strip on narrow mobile (zero drawer taps!) */}
      {staples.length > 0 && (
        <div className="md:hidden space-y-1.5">
          <div className="flex items-center justify-between px-0.5">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400">
              Schnell-Favoriten (+1)
            </span>
            <button
              type="button"
              onClick={() => setDrawerOpen(true)}
              className="text-xs font-medium text-[#2E7D5B] cursor-pointer"
            >
              Suche & alle →
            </button>
          </div>
          <div className="flex gap-2 overflow-x-auto pb-1 -mx-3.5 px-3.5">
            {staples.slice(0, 6).map((p) => (
              <button
                key={`qs-${p.picnic_id}`}
                type="button"
                disabled={busyId === p.picnic_id}
                onClick={() => handleModify(p.picnic_id, 'add', p.name)}
                className="shrink-0 inline-flex items-center gap-1.5 pl-2 pr-3 py-1.5 rounded-full bg-white border border-[#E5E4DF] hover:border-[#2E7D5B] text-xs font-medium text-[#18181B] cursor-pointer disabled:opacity-50"
              >
                <span className="w-5 h-5 rounded-full bg-[#2E7D5B]/12 text-[#2E7D5B] flex items-center justify-center">
                  <Plus className="w-3 h-3" />
                </span>
                <span className="max-w-[130px] truncate">{p.name}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Smart Restock: Recurring staples from recent deliveries missing in live cart */}
      {cart && cart.restock_suggestions.length > 0 && (
        <section className="bg-white border border-[#E5E4DF] rounded-2xl px-4 py-3 space-y-2">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400">
              Fehlt diese Woche noch?
            </span>
            <span className="text-[11px] text-zinc-400">Oft gekauft, noch nicht im Korb</span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {cart.restock_suggestions.map((item) => (
              <button
                key={`restock-${item.picnic_id}`}
                type="button"
                disabled={busyId === item.picnic_id}
                onClick={() => handleModify(item.picnic_id, 'add', item.name)}
                className="inline-flex items-center gap-1.5 pl-2 pr-2.5 py-1 rounded-full bg-[#FAF9F6] border border-[#E5E4DF] hover:border-[#2E7D5B] hover:bg-[#2E7D5B]/5 text-xs text-[#18181B] transition cursor-pointer disabled:opacity-50"
              >
                <span className="w-4 h-4 rounded-full bg-[#2E7D5B]/12 text-[#2E7D5B] flex items-center justify-center shrink-0">
                  <Plus className="w-2.5 h-2.5" />
                </span>
                <span className="font-medium max-w-[160px] truncate">{item.name}</span>
                <span className="text-[10px] text-zinc-400 tabular-nums">
                  {item.hits_in_recent_deliveries}/{item.recent_deliveries_checked}
                </span>
              </button>
            ))}
          </div>
        </section>
      )}

      {/* Very unobtrusive, collapsed-by-default Mealie week reminder */}
      {mealieEntries.length > 0 && (
        <div className="px-1">
          <button
            type="button"
            onClick={() => setMealieOpen((v) => !v)}
            className="inline-flex items-center gap-1.5 text-xs text-zinc-500 hover:text-[#18181B] transition cursor-pointer"
          >
            <Utensils className="w-3.5 h-3.5 text-zinc-400" />
            <span>
              Wochenplan ({mealieEntries.length}{' '}
              {mealieEntries.length === 1 ? 'Gericht' : 'Gerichte'})
            </span>
            {mealieOpen ? (
              <ChevronUp className="w-3.5 h-3.5 text-zinc-400" />
            ) : (
              <ChevronDown className="w-3.5 h-3.5 text-zinc-400" />
            )}
          </button>
          {mealieOpen && (
            <div className="mt-2 bg-white/80 border border-[#E5E4DF] rounded-xl px-3.5 py-2.5 flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-zinc-600">
              {mealieEntries.map((entry) => {
                const day = new Date(`${entry.plan_date}T12:00:00`).toLocaleDateString('de-DE', {
                  weekday: 'short',
                })
                const title = entry.recipe?.name || entry.title
                const score = entry.recipe?.health_score
                return (
                  <span key={entry.id} className="inline-flex items-center gap-1.5">
                    <span className="text-zinc-400 font-medium">{day}:</span>
                    <span className="text-[#18181B]">{title}</span>
                    {score != null && (
                      <span className="text-[10px] text-[#2E7D5B] tabular-nums font-medium">
                        ({score})
                      </span>
                    )}
                  </span>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* Split Layout: Foldable-ready 2 columns starting at md (768px+) */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-4">
        <section className="md:col-span-7 bg-white border border-[#E5E4DF] rounded-2xl p-4 sm:p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-[#18181B]">Aktuelle Artikel</h2>
            <span className="text-xs text-zinc-400 tabular-nums">
              {cart?.items.length ?? 0} Positionen
            </span>
          </div>

          {!cart || cart.items.length === 0 ? (
            <p className="py-8 text-sm text-zinc-400 text-center">
              Dein Warenkorb ist aktuell leer. Füge Produkte aus vergangenen Einkäufen oder der
              Picnic-Suche hinzu.
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
                  <div className="flex items-center gap-2.5 sm:gap-3 min-w-0">
                    <ProductThumb src={item.image_url} alt={item.name} />
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className="text-sm font-medium text-[#18181B] truncate">
                          {item.name}
                        </span>
                        {item.ignored && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-100 text-zinc-500 shrink-0">
                            Ignoriert
                          </span>
                        )}
                      </div>
                      <div className="mt-1 flex items-center flex-wrap gap-1.5">
                        <BucketBadge bucket={item.bucket} />
                        <NovaBadge nova={item.nova_group} />
                        <span className="text-[11px] text-zinc-500 tabular-nums">
                          {formatEuro(item.price_cents)}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Larger mobile-friendly 36x36px touch targets */}
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
                        className={`w-9 h-9 rounded-xl border flex items-center justify-center transition cursor-pointer disabled:opacity-50 ${
                          item.ignored
                            ? 'border-[#2E7D5B]/30 bg-[#2E7D5B]/8 text-[#2E7D5B]'
                            : 'border-[#E5E4DF] bg-[#FAF9F6] hover:bg-zinc-100 text-zinc-400 hover:text-zinc-700'
                        }`}
                      >
                        {item.ignored ? (
                          <Eye className="w-4 h-4" />
                        ) : (
                          <EyeOff className="w-4 h-4" />
                        )}
                      </button>
                    )}

                    <button
                      type="button"
                      disabled={busyId === item.picnic_id}
                      onClick={() => handleModify(item.picnic_id, 'remove', item.name)}
                      aria-label={`${item.name} entfernen`}
                      className="w-9 h-9 rounded-xl border border-[#E5E4DF] bg-[#FAF9F6] hover:bg-zinc-100 flex items-center justify-center text-zinc-700 cursor-pointer disabled:opacity-50"
                    >
                      <Minus className="w-4 h-4" />
                    </button>
                    <span className="w-5 text-center text-sm font-semibold tabular-nums">
                      {item.quantity}
                    </span>
                    <button
                      type="button"
                      disabled={busyId === item.picnic_id}
                      onClick={() => handleModify(item.picnic_id, 'add', item.name)}
                      aria-label={`${item.name} hinzufügen`}
                      className="w-9 h-9 rounded-xl border border-[#E5E4DF] bg-[#FAF9F6] hover:bg-zinc-100 flex items-center justify-center text-zinc-700 cursor-pointer disabled:opacity-50"
                    >
                      <Plus className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Foldable & Desktop Side Panel (md+) */}
        <aside className="hidden md:block md:col-span-5 bg-white border border-[#E5E4DF] rounded-2xl p-4 sm:p-5 h-fit sticky top-20">
          {renderAddPanel(false)}
        </aside>
      </div>

      {/* Mobile Bottom Sheet Drawer — backdrop tap closes cleanly, zero nested scroll */}
      {drawerOpen && (
        <div
          onClick={() => setDrawerOpen(false)}
          className="fixed inset-0 z-50 md:hidden flex items-end bg-black/35 backdrop-blur-[1px]"
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="w-full max-h-[85vh] overflow-y-auto bg-white rounded-t-3xl p-5 border-t border-[#E5E4DF] pb-8"
          >
            <div className="flex items-center justify-between mb-3">
              <div className="w-10 h-1 rounded-full bg-zinc-200 mx-auto" />
              <button
                type="button"
                onClick={() => setDrawerOpen(false)}
                aria-label="Schließen"
                className="w-9 h-9 rounded-xl text-zinc-500 hover:bg-zinc-100 flex items-center justify-center"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            {renderAddPanel(true)}
          </div>
        </div>
      )}
    </div>
  )
}
