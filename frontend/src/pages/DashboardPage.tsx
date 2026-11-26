import {
  ArrowRight,
  KeyRound,
  PlayCircle,
  RefreshCw,
  ShoppingBag,
  Sparkles,
  Utensils,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { api, formatEuro, type DashboardResponse } from '../api/client'
import { DriversCard } from '../components/DriversCard'
import { MealieRecipeCard } from '../components/MealieRecipeCard'
import { GoalChecklist, StreakAndBestBadges, TierPill } from '../components/QualityBadges'
import { RatioBars } from '../components/RatioBars'
import { TrendChart } from '../components/TrendChart'

interface Props {
  onNavigate: (tab: 'dashboard' | 'cart' | 'history' | 'products' | 'settings') => void
  onCartCountChange?: (count: number) => void
  onDemoModeChange?: (demo: boolean) => void
}

export function DashboardPage({ onNavigate, onCartCountChange, onDemoModeChange }: Props) {
  const [data, setData] = useState<DashboardResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [startingDemo, setStartingDemo] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    try {
      setError(null)
      const res = await api.getDashboard()
      setData(res)
      onCartCountChange?.(res.live_cart_item_count)
      onDemoModeChange?.(res.demo_mode)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Laden fehlgeschlagen')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const handleSync = async () => {
    setSyncing(true)
    try {
      await api.triggerSync()
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sync fehlgeschlagen')
    } finally {
      setSyncing(false)
    }
  }

  const handleEnableDemo = async () => {
    setStartingDemo(true)
    try {
      await api.saveAppSettings({ demo_mode: true })
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Demo-Modus konnte nicht aktiviert werden')
    } finally {
      setStartingDemo(false)
    }
  }

  if (loading) {
    return (
      <div className="space-y-4 animate-pulse">
        <div className="h-44 rounded-2xl bg-white border border-[#E5E4DF]" />
        <div className="h-56 rounded-2xl bg-white border border-[#E5E4DF]" />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="bg-white border border-[#E5E4DF] rounded-2xl p-6 text-center">
        <p className="text-sm text-zinc-600">{error ?? 'Keine Daten verfügbar.'}</p>
        <button
          type="button"
          onClick={load}
          className="mt-3 px-4 py-2 text-sm font-medium rounded-xl bg-[#18181B] text-white cursor-pointer"
        >
          Erneut versuchen
        </button>
      </div>
    )
  }

  const metrics = data.current_week_metrics
  const delta = data.delta_vs_avg

  // Clean Cold-Start Onboarding when neither deliveries nor live cart exist yet
  if (!metrics && data.live_cart_item_count === 0) {
    return (
      <section className="bg-white border border-[#E5E4DF] rounded-3xl p-6 sm:p-10 max-w-2xl mx-auto text-center space-y-5">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#2E7D5B]/10 text-[#2E7D5B] text-xs font-semibold">
          Willkommen bei Stats for Picnic
        </div>
        <div className="space-y-2">
          <h1 className="text-2xl font-semibold tracking-tight text-[#18181B]">
            Ruhige Einkaufsanalyse ohne Kalorienzählen
          </h1>
          <p className="text-sm text-zinc-500 max-w-lg mx-auto leading-relaxed">
            Verbinde einmalig dein Picnic-Konto (per 2FA) oder schau dir zuerst alles unverbindlich
            mit realistischen deutschen Beispieldaten im Demo-Modus an.
          </p>
        </div>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-2">
          <button
            type="button"
            onClick={() => onNavigate('settings')}
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl bg-[#18181B] hover:bg-zinc-800 text-white text-sm font-medium transition cursor-pointer"
          >
            <KeyRound className="w-4 h-4" />
            Picnic jetzt verbinden
          </button>
          <button
            type="button"
            disabled={startingDemo}
            onClick={handleEnableDemo}
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl border border-[#2E7D5B]/30 bg-[#2E7D5B]/8 hover:bg-[#2E7D5B]/15 text-[#2E7D5B] text-sm font-medium transition cursor-pointer disabled:opacity-50"
          >
            <PlayCircle className="w-4 h-4" />
            {startingDemo ? 'Lädt Demo…' : 'Im Demo-Modus testen'}
          </button>
        </div>
      </section>
    )
  }

  return (
    <div className="space-y-5">
      {/* Subtle Re-Auth Banner when Picnic session expired */}
      {data.picnic_status === 'reauth_required' && (
        <div className="bg-[#D97706]/10 border border-[#D97706]/30 rounded-2xl p-4 flex items-center justify-between gap-3">
          <div className="text-sm text-[#92400E]">
            <strong>Picnic-Sitzung abgelaufen:</strong> Bitte 2FA in den Einstellungen kurz erneuern.
          </div>
          <button
            type="button"
            onClick={() => onNavigate('settings')}
            className="shrink-0 px-3 py-1.5 rounded-xl bg-[#18181B] text-white text-xs font-medium cursor-pointer"
          >
            Zu Einstellungen
          </button>
        </div>
      )}

      {/* Subtle Pending Enrichment Banner */}
      {data.pending_enrichment_count > 0 && (
        <div className="bg-white border border-[#E5E4DF] rounded-2xl px-4 py-3 flex items-center justify-between gap-3">
          <span className="text-xs text-zinc-600">
            <strong>{data.pending_enrichment_count}</strong> neue Produkte warten noch auf
            Nährwert-Anreicherung.
          </span>
          <button
            type="button"
            onClick={() => onNavigate('products')}
            className="shrink-0 text-xs font-medium text-[#2E7D5B] hover:underline cursor-pointer"
          >
            In Produkte ansehen →
          </button>
        </div>
      )}

      {/* Hero Row: Weekly Score + Live Cart Pre-Checkout shortcut */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <section className="lg:col-span-2 bg-white border border-[#E5E4DF] rounded-2xl p-5 sm:p-6">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="flex items-center flex-wrap gap-2">
                <span className="text-xs font-medium uppercase tracking-wider text-zinc-400">
                  Wochenqualität · {data.current_week_iso}
                </span>
                {metrics && <TierPill tier={metrics.tier} />}
              </div>

              <div className="mt-2 flex items-baseline flex-wrap gap-3">
                <span className="text-5xl font-semibold tracking-tight text-[#18181B] tabular-nums">
                  {metrics ? metrics.score : '—'}
                </span>
                <span className="text-base text-zinc-400 font-medium">/100</span>
                {delta != null && (
                  <span
                    className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold tabular-nums ${
                      delta >= 0
                        ? 'bg-[#2E7D5B]/10 text-[#2E7D5B]'
                        : 'bg-[#D97706]/12 text-[#B45309]'
                    }`}
                  >
                    {delta >= 0 ? `+${delta}` : delta} vs. 8-Wo.-Schnitt
                  </span>
                )}
              </div>
            </div>

            <button
              type="button"
              onClick={handleSync}
              disabled={syncing}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-[#E5E4DF] bg-[#FAF9F6] hover:bg-zinc-100 text-xs font-medium text-zinc-700 transition cursor-pointer disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${syncing ? 'animate-spin' : ''}`} />
              {syncing ? 'Lädt…' : 'Sync'}
            </button>
          </div>

          {metrics && (
            <div className="mt-3 space-y-3">
              <StreakAndBestBadges
                streakWeeks={data.healthy_streak_weeks}
                isPersonalBest={data.is_personal_best}
              />
              <p className="text-sm text-zinc-600 leading-relaxed">{metrics.insight_text}</p>
              <GoalChecklist tier={metrics.tier} />
              <div className="pt-1">
                <RatioBars metrics={metrics} />
              </div>
              {metrics.ignored_item_count > 0 && (
                <p className="text-xs text-zinc-400">
                  {metrics.included_item_count} Lebensmittel ausgewertet ·{' '}
                  {metrics.ignored_item_count} Haushalts-/Familienartikel ignoriert.
                </p>
              )}
            </div>
          )}
        </section>

        {/* Live Pre-Checkout Cart Quick Card */}
        <section className="bg-white border border-[#E5E4DF] rounded-2xl p-5 sm:p-6 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium uppercase tracking-wider text-zinc-400">
                Live Warenkorb
              </span>
              <ShoppingBag className="w-4 h-4 text-[#2E7D5B]" />
            </div>

            {data.live_cart_item_count > 0 ? (
              <>
                <div className="mt-3 flex items-baseline gap-2">
                  <span className="text-4xl font-semibold tabular-nums text-[#18181B]">
                    {data.live_cart_score ?? '—'}
                  </span>
                  <span className="text-sm text-zinc-400">/100 Pre-Checkout</span>
                </div>
                <div className="mt-2 text-sm text-zinc-600 tabular-nums">
                  {data.live_cart_item_count} Artikel · {formatEuro(data.live_cart_total_cents)}
                </div>
                <p className="mt-3 text-xs text-zinc-500 leading-relaxed">
                  Prüfe deinen offenen Picnic-Warenkorb vor dem Bestellen, nutze Quick-Wins und
                  ergänze gesunde Favoriten mit einem Klick.
                </p>
              </>
            ) : (
              <p className="mt-4 text-sm text-zinc-500">Aktuell kein offener Picnic-Warenkorb.</p>
            )}
          </div>

          <button
            type="button"
            onClick={() => onNavigate('cart')}
            className="mt-5 w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-[#18181B] hover:bg-zinc-800 text-white text-sm font-medium transition cursor-pointer"
          >
            Pre-Checkout öffnen
            <ArrowRight className="w-4 h-4" />
          </button>
        </section>
      </div>

      {/* Positive & Negative Drivers */}
      {metrics && (
        <DriversCard
          positive={metrics.positive_drivers}
          negative={metrics.negative_drivers}
        />
      )}

      {/* 8-Week Trend */}
      <section className="bg-white border border-[#E5E4DF] rounded-2xl p-5 sm:p-6">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="text-sm font-semibold text-[#18181B]">8-Wochen-Verlauf</h2>
            <p className="text-xs text-zinc-500">
              Haushaltsunabhängiger Qualitäts-Trend statt täglichem Kalorienzählen
            </p>
          </div>
          {data.avg_8_weeks != null && (
            <span className="text-xs text-zinc-500 tabular-nums">
              Schnitt: <strong className="text-[#18181B]">{data.avg_8_weeks}</strong>
              {data.best_8_week_score != null && (
                <span className="ml-2 text-zinc-400">· Bestwert: {data.best_8_week_score}</span>
              )}
            </span>
          )}
        </div>
        <TrendChart points={data.trend_8_weeks} />
      </section>

      {/* Optional Mealie Weekly Recipes */}
      {data.mealie_configured && (
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Utensils className="w-4 h-4 text-[#2E7D5B]" />
              <h2 className="text-sm font-semibold text-[#18181B]">
                Geplante Rezepte diese Woche (Mealie)
              </h2>
            </div>
            <span className="text-xs text-zinc-400">{data.current_week_iso}</span>
          </div>

          {data.weekly_mealie_entries.length === 0 ? (
            <div className="bg-white border border-[#E5E4DF] rounded-2xl p-5 text-sm text-zinc-500 flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-zinc-400" />
              Für {data.current_week_iso} sind aktuell keine Mealie-Rezepte geplant.
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
              {data.weekly_mealie_entries.map((entry) => (
                <MealieRecipeCard key={entry.id} entry={entry} />
              ))}
            </div>
          )}
        </section>
      )}
    </div>
  )
}
