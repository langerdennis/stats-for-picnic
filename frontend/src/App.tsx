import {
  LayoutGrid,
  Package,
  Receipt,
  Settings,
  ShoppingBag,
  Sprout,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from './api/client'
import { CartPage } from './pages/CartPage'
import { DashboardPage } from './pages/DashboardPage'
import { HistoryPage } from './pages/HistoryPage'
import { ProductsPage } from './pages/ProductsPage'
import { SettingsPage } from './pages/SettingsPage'

type TabKey = 'dashboard' | 'cart' | 'history' | 'products' | 'settings'

const NAV_ITEMS: { key: TabKey; label: string; icon: typeof LayoutGrid }[] = [
  { key: 'dashboard', label: 'Übersicht', icon: LayoutGrid },
  { key: 'cart', label: 'Warenkorb', icon: ShoppingBag },
  { key: 'history', label: 'Einkäufe', icon: Receipt },
  { key: 'products', label: 'Produkte', icon: Package },
  { key: 'settings', label: 'Einstellungen', icon: Settings },
]

export default function App() {
  const [tab, setTab] = useState<TabKey>('dashboard')
  const [cartCount, setCartCount] = useState<number>(0)
  const [demoMode, setDemoMode] = useState<boolean>(false)

  useEffect(() => {
    api
      .getDashboard()
      .then((d) => {
        setCartCount(d.live_cart_item_count)
        setDemoMode(d.demo_mode)
      })
      .catch(() => {})
  }, [])

  return (
    <div className="min-h-screen bg-[#F8F7F4] text-[#18181B] pb-24 md:pb-12">
      {/* Top Bar */}
      <header className="sticky top-0 z-30 bg-[#F8F7F4]/90 backdrop-blur-md border-b border-[#E5E4DF]">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 h-15 flex items-center justify-between gap-4">
          <button
            type="button"
            onClick={() => setTab('dashboard')}
            className="flex items-center gap-2.5 text-left cursor-pointer"
          >
            <div className="w-8 h-8 rounded-xl bg-[#2E7D5B] text-white flex items-center justify-center">
              <Sprout className="w-4 h-4" />
            </div>
            <div>
              <div className="text-sm font-semibold tracking-tight leading-none">
                Stats for Picnic
              </div>
              <div className="text-[11px] text-zinc-500 mt-0.5 leading-none">
                {demoMode ? 'Demo-Modus · Ruhige Einkaufsanalyse' : 'Ruhige Einkaufsanalyse'}
              </div>
            </div>
          </button>

          {/* Desktop Pill Nav */}
          <nav
            aria-label="Hauptnavigation"
            className="hidden md:flex items-center gap-1 p-1 rounded-full bg-white border border-[#E5E4DF]"
          >
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon
              const active = tab === item.key
              return (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => setTab(item.key)}
                  className={`inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-xs font-medium transition cursor-pointer ${
                    active
                      ? 'bg-[#18181B] text-white'
                      : 'text-zinc-600 hover:text-[#18181B] hover:bg-[#FAF9F6]'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  <span>{item.label}</span>
                  {item.key === 'cart' && cartCount > 0 && (
                    <span
                      className={`ml-0.5 px-1.5 py-0.2 rounded-full text-[10px] font-semibold tabular-nums ${
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

          {/* Mobile Demo Pill */}
          {demoMode && (
            <span className="md:hidden px-2 py-0.5 rounded-full text-[10px] font-semibold bg-[#2E7D5B]/10 text-[#2E7D5B] border border-[#2E7D5B]/20">
              DEMO
            </span>
          )}
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-5xl mx-auto px-4 sm:px-6 pt-5 sm:pt-7">
        {tab === 'dashboard' && (
          <DashboardPage
            onNavigate={setTab}
            onCartCountChange={setCartCount}
            onDemoModeChange={setDemoMode}
          />
        )}
        {tab === 'cart' && <CartPage onCartCountChange={setCartCount} />}
        {tab === 'history' && <HistoryPage onCartCountChange={setCartCount} />}
        {tab === 'products' && <ProductsPage onCartCountChange={setCartCount} />}
        {tab === 'settings' && <SettingsPage onDemoModeChange={setDemoMode} />}
      </main>

      {/* Mobile Bottom Navigation */}
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
                onClick={() => setTab(item.key)}
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
