import {
  AlertTriangle,
  LayoutGrid,
  LogIn,
  LogOut,
  Package,
  Receipt,
  Settings,
  ShoppingBag,
  Sprout,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { api, type OIDCStatus } from './api/client'
import { CartPage } from './pages/CartPage'
import { DashboardPage } from './pages/DashboardPage'
import { HistoryPage } from './pages/HistoryPage'
import { ProductsPage } from './pages/ProductsPage'
import { SettingsPage } from './pages/SettingsPage'

type TabKey = 'dashboard' | 'cart' | 'history' | 'products' | 'settings'

const VALID_TABS: TabKey[] = ['dashboard', 'cart', 'history', 'products', 'settings']

const NAV_ITEMS: { key: TabKey; label: string; icon: typeof LayoutGrid }[] = [
  { key: 'dashboard', label: 'Übersicht', icon: LayoutGrid },
  { key: 'cart', label: 'Warenkorb', icon: ShoppingBag },
  { key: 'history', label: 'Einkäufe', icon: Receipt },
  { key: 'products', label: 'Produkte', icon: Package },
  { key: 'settings', label: 'Einstellungen', icon: Settings },
]

function readRouteFromHash(): { tab: TabKey; historySub: 'deliveries' | 'stats' } {
  const raw = window.location.hash.replace(/^#\/?/, '').trim()
  if (raw === 'stats') {
    return { tab: 'history', historySub: 'stats' }
  }
  const candidate = raw as TabKey
  return {
    tab: VALID_TABS.includes(candidate) ? candidate : 'dashboard',
    historySub: 'deliveries',
  }
}

export default function App() {
  const initialRoute = readRouteFromHash()
  const [tab, setTab] = useState<TabKey>(initialRoute.tab)
  const [historySub, setHistorySub] = useState<'deliveries' | 'stats'>(initialRoute.historySub)
  const [cartCount, setCartCount] = useState<number>(0)
  const [demoMode, setDemoMode] = useState<boolean>(false)
  const [picnicReauth, setPicnicReauth] = useState<boolean>(false)
  const [oidc, setOidc] = useState<OIDCStatus | null>(null)
  const [oidcChecking, setOidcChecking] = useState(true)

  const navigate = (next: TabKey, sub?: 'deliveries' | 'stats') => {
    setTab(next)
    if (next === 'history') {
      const nextSub = sub ?? 'deliveries'
      setHistorySub(nextSub)
      const targetHash = nextSub === 'stats' ? '#stats' : '#history'
      if (window.location.hash !== targetHash) {
        window.history.pushState(null, '', targetHash)
      }
    } else {
      const targetHash = `#${next}`
      if (window.location.hash !== targetHash) {
        window.history.pushState(null, '', targetHash)
      }
    }
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  useEffect(() => {
    const onHashChange = () => {
      const route = readRouteFromHash()
      setTab(route.tab)
      setHistorySub(route.historySub)
    }
    const onOidcRequired = () => {
      setOidc((prev) => ({
        enabled: true,
        authenticated: false,
        provider_name: prev?.provider_name || 'PocketID',
        user_email: null,
        user_name: null,
      }))
    }
    window.addEventListener('hashchange', onHashChange)
    window.addEventListener('sfp:oidc-required', onOidcRequired)
    return () => {
      window.removeEventListener('hashchange', onHashChange)
      window.removeEventListener('sfp:oidc-required', onOidcRequired)
    }
  }, [])

  useEffect(() => {
    api
      .getOIDCStatus()
      .then((status) => {
        setOidc(status)
        if (!status.enabled || status.authenticated) {
          api
            .getDashboard()
            .then((d) => {
              setCartCount(d.live_cart_item_count)
              setDemoMode(d.demo_mode)
              setPicnicReauth(d.picnic_status === 'reauth_required')
            })
            .catch(() => {})
        }
      })
      .catch(() => {
        setOidc({
          enabled: false,
          authenticated: true,
          provider_name: 'PocketID',
          user_email: null,
          user_name: null,
        })
      })
      .finally(() => setOidcChecking(false))
  }, [])

  const handleLogout = async () => {
    await api.logoutOIDC().catch(() => {})
    window.location.href = '/'
  }

  const oidcError =
    typeof window !== 'undefined'
      ? new URLSearchParams(window.location.search).get('oidc_error')
      : null

  if (oidcChecking) {
    return (
      <div className="min-h-screen bg-[#F8F7F4] flex items-center justify-center p-6">
        <div className="flex items-center gap-2.5 text-sm text-zinc-500">
          <div className="w-7 h-7 rounded-xl bg-[#2E7D5B] text-white flex items-center justify-center">
            <Sprout className="w-4 h-4" />
          </div>
          <span>Lädt…</span>
        </div>
      </div>
    )
  }

  // Calm PocketID / OIDC Login Gate
  if (oidc?.enabled && !oidc.authenticated) {
    return (
      <div className="min-h-screen bg-[#F8F7F4] text-[#18181B] flex items-center justify-center p-5">
        <div className="bg-white border border-[#E5E4DF] rounded-3xl p-7 sm:p-9 max-w-sm w-full text-center space-y-5">
          <div className="w-12 h-12 mx-auto rounded-2xl bg-[#2E7D5B] text-white flex items-center justify-center">
            <Sprout className="w-6 h-6" />
          </div>
          <div className="space-y-1.5">
            <h1 className="text-xl font-semibold tracking-tight">Stats for Picnic</h1>
            <p className="text-sm text-zinc-500 leading-relaxed">
              Geschützter Haushalts-Zugang über <strong>{oidc.provider_name}</strong>.
            </p>
          </div>

          {oidcError && (
            <div className="text-xs text-[#92400E] bg-[#D97706]/10 border border-[#D97706]/30 rounded-xl p-3 text-left">
              {oidcError}
            </div>
          )}

          <a
            href="/api/auth/oidc/login"
            className="w-full inline-flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-[#18181B] hover:bg-zinc-800 text-white text-sm font-medium transition"
          >
            <LogIn className="w-4 h-4" />
            Mit {oidc.provider_name} anmelden
          </a>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#F8F7F4] text-[#18181B] pb-24 md:pb-12 overflow-x-hidden">
      {/* Top Bar — optimized for Cover Screens (340px), Unfolded Foldables (670–840px) & Desktop */}
      <header className="sticky top-0 z-30 bg-[#F8F7F4]/92 backdrop-blur-md border-b border-[#E5E4DF]">
        <div className="max-w-5xl mx-auto px-3.5 sm:px-6 h-14 sm:h-15 flex items-center justify-between gap-2.5">
          <button
            type="button"
            onClick={() => navigate('dashboard')}
            className="flex items-center gap-2 text-left cursor-pointer min-w-0"
          >
            <div className="w-8 h-8 rounded-xl bg-[#2E7D5B] text-white flex items-center justify-center shrink-0">
              <Sprout className="w-4 h-4" />
            </div>
            <div className="min-w-0">
              <div className="text-sm font-semibold tracking-tight leading-none truncate">
                Stats for Picnic
              </div>
              <div className="text-[11px] text-zinc-500 mt-0.5 leading-none truncate hidden sm:block">
                {demoMode ? 'Demo-Modus · Ruhige Einkaufsanalyse' : 'Ruhige Einkaufsanalyse'}
              </div>
            </div>
          </button>

          {/* Foldable & Desktop Pill Nav (md+) */}
          <nav
            aria-label="Hauptnavigation"
            className="hidden md:flex items-center gap-0.5 lg:gap-1 p-1 rounded-full bg-white border border-[#E5E4DF]"
          >
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon
              const active = tab === item.key
              return (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => navigate(item.key)}
                  className={`inline-flex items-center gap-1.5 px-2.5 lg:px-3.5 py-1.5 rounded-full text-xs font-medium transition cursor-pointer ${
                    active
                      ? 'bg-[#18181B] text-white'
                      : 'text-zinc-600 hover:text-[#18181B] hover:bg-[#FAF9F6]'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5 shrink-0" />
                  <span>{item.label}</span>
                  {item.key === 'cart' && cartCount > 0 && (
                    <span
                      className={`ml-0.5 px-1.5 rounded-full text-[10px] font-semibold tabular-nums ${
                        active ? 'bg-white/20 text-white' : 'bg-[#2E7D5B]/12 text-[#2E7D5B]'
                      }`}
                    >
                      {cartCount}
                    </span>
                  )}
                </button>
              )
            })}
          </nav>

          {/* Right Status: Demo pill & OIDC Logout */}
          <div className="flex items-center gap-1.5 shrink-0">
            {demoMode && (
              <span className="md:hidden px-2 py-0.5 rounded-full text-[10px] font-semibold bg-[#2E7D5B]/10 text-[#2E7D5B] border border-[#2E7D5B]/20">
                DEMO
              </span>
            )}
            {oidc?.enabled && oidc.authenticated && (
              <button
                type="button"
                onClick={handleLogout}
                title={`Abmelden (${oidc.user_email || oidc.user_name || oidc.provider_name})`}
                className="p-2 rounded-xl border border-[#E5E4DF] bg-white hover:bg-zinc-100 text-zinc-600 cursor-pointer"
              >
                <LogOut className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-5xl mx-auto px-3.5 sm:px-6 pt-4 sm:pt-6">
        {picnicReauth && tab !== 'settings' && (
          <div className="mb-4 bg-[#D97706]/10 border border-[#D97706]/30 rounded-2xl px-4 py-3 flex flex-wrap items-center justify-between gap-2.5 text-xs text-[#92400E]">
            <div className="flex items-center gap-2 min-w-0">
              <AlertTriangle className="w-4 h-4 shrink-0 text-[#B45309]" />
              <span>
                Deine Picnic-Sitzung ist abgelaufen — bitte kurz per 2FA neu anmelden.
              </span>
            </div>
            <button
              type="button"
              onClick={() => navigate('settings')}
              className="shrink-0 px-3 py-1.5 rounded-xl bg-[#B45309] hover:bg-[#92400E] text-white font-medium cursor-pointer"
            >
              Neu anmelden →
            </button>
          </div>
        )}
        {tab === 'dashboard' && (
          <DashboardPage
            onNavigate={navigate}
            onOpenStats={() => navigate('history', 'stats')}
            onCartCountChange={setCartCount}
            onDemoModeChange={setDemoMode}
          />
        )}
        {tab === 'cart' && <CartPage onCartCountChange={setCartCount} />}
        {tab === 'history' && (
          <HistoryPage
            initialSubTab={historySub}
            onSubTabChange={(sub) => navigate('history', sub)}
            onCartCountChange={setCartCount}
          />
        )}
        {tab === 'products' && <ProductsPage onCartCountChange={setCartCount} />}
        {tab === 'settings' && <SettingsPage onDemoModeChange={setDemoMode} />}
      </main>

      {/* Mobile Bottom Navigation (Cover Screens & Narrow Phones) */}
      <nav
        aria-label="Mobile Navigation"
        className="md:hidden fixed bottom-0 inset-x-0 z-40 bg-white/95 backdrop-blur-md border-t border-[#E5E4DF] pb-[env(safe-area-inset-bottom)]"
      >
        <div className="grid grid-cols-5 h-16">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon
            const active = tab === item.key
            return (
              <button
                key={item.key}
                type="button"
                onClick={() => navigate(item.key)}
                className={`relative flex flex-col items-center justify-center gap-1 text-[10px] font-medium transition ${
                  active ? 'text-[#2E7D5B]' : 'text-zinc-500'
                }`}
              >
                <div className="relative">
                  <Icon className="w-5 h-5" />
                  {item.key === 'cart' && cartCount > 0 && (
                    <span className="absolute -top-1.5 -right-2.5 min-w-4 h-4 px-1 rounded-full bg-[#2E7D5B] text-white text-[9px] font-bold flex items-center justify-center tabular-nums">
                      {cartCount}
                    </span>
                  )}
                </div>
                <span>{item.label}</span>
              </button>
            )
          })}
        </div>
      </nav>
    </div>
  )
}
