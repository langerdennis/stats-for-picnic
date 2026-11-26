import {
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Copy,
  Download,
  KeyRound,
  Monitor,
  RefreshCw,
  ShieldCheck,
  Sliders,
  Sparkles,
  Trash2,
  Unplug,
  Utensils,
  Wand2,
} from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { api, type ScoringTargets, type SettingsStatus } from '../api/client'

interface Props {
  onDemoModeChange?: (demo: boolean) => void
}

function generateRandomApiKey(): string {
  const bytes = new Uint8Array(24)
  crypto.getRandomValues(bytes)
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
  return `sfp_${hex}`
}

function CollapsibleCard({
  icon,
  title,
  subtitle,
  badge,
  badgeTone = 'neutral',
  open,
  onToggle,
  children,
}: {
  icon: ReactNode
  title: string
  subtitle?: string
  badge: string
  badgeTone?: 'sage' | 'amber' | 'neutral'
  open: boolean
  onToggle: () => void
  children: ReactNode
}) {
  const badgeCls =
    badgeTone === 'sage'
      ? 'bg-[#2E7D5B]/10 text-[#2E7D5B]'
      : badgeTone === 'amber'
        ? 'bg-[#D97706]/15 text-[#B45309]'
        : 'bg-zinc-100 text-zinc-500'

  return (
    <section className="bg-white border border-[#E5E4DF] rounded-2xl overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        className="w-full p-4 sm:p-5 flex items-center justify-between gap-3 text-left hover:bg-[#FAF9F6]/70 transition cursor-pointer"
      >
        <div className="flex items-center gap-2.5 min-w-0">
          <span className="text-[#2E7D5B] shrink-0">{icon}</span>
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-[#18181B]">{title}</h3>
            {subtitle && <p className="text-xs text-zinc-500 truncate">{subtitle}</p>}
          </div>
        </div>
        <div className="shrink-0 flex items-center gap-2">
          <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${badgeCls}`}>
            {badge}
          </span>
          {open ? (
            <ChevronUp className="w-4 h-4 text-zinc-400" />
          ) : (
            <ChevronDown className="w-4 h-4 text-zinc-400" />
          )}
        </div>
      </button>
      {open && <div className="px-4 sm:px-5 pb-5 pt-1 border-t border-[#ECEBE6]">{children}</div>}
    </section>
  )
}

type SectionKey = 'app' | 'picnic' | 'oidc' | 'llm' | 'mealie' | 'tesserae'

export function SettingsPage({ onDemoModeChange }: Props) {
  const [status, setStatus] = useState<SettingsStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [feedback, setFeedback] = useState<{ type: 'ok' | 'err'; text: string } | null>(null)
  const [openSections, setOpenSections] = useState<Record<SectionKey, boolean>>({
    app: true,
    picnic: true,
    oidc: false,
    llm: false,
    mealie: false,
    tesserae: false,
  })

  // App runtime settings form state
  const [demoMode, setDemoMode] = useState(false)
  const [syncInterval, setSyncInterval] = useState(60)
  const [apiKeyInput, setApiKeyInput] = useState('')
  const [scoringTargets, setScoringTargets] = useState<ScoringTargets>({
    protein_per_1000_kcal: 35,
    fresh_share_pct: 35,
    nova_1_2_share_pct: 75,
    snack_share_pct: 15,
  })

  // Picnic 2FA form state
  const [country, setCountry] = useState<'DE' | 'NL'>('DE')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [twoFaStep, setTwoFaStep] = useState(false)
  const [otpCode, setOtpCode] = useState('')

  // Mealie form state
  const [mealieUrl, setMealieUrl] = useState('')
  const [mealieToken, setMealieToken] = useState('')

  // LLM form state
  const [llmBaseUrl, setLlmBaseUrl] = useState('https://api.deepseek.com')
  const [llmModel, setLlmModel] = useState('deepseek-flash')
  const [llmApiKey, setLlmApiKey] = useState('')
  const [llmUseResponses, setLlmUseResponses] = useState(true)

  // OIDC / PocketID form state
  const [oidcEnabled, setOidcEnabled] = useState(false)
  const [oidcProviderName, setOidcProviderName] = useState('PocketID')
  const [oidcIssuerUrl, setOidcIssuerUrl] = useState('')
  const [oidcClientId, setOidcClientId] = useState('')
  const [oidcClientSecret, setOidcClientSecret] = useState('')
  const [oidcAllowedEmails, setOidcAllowedEmails] = useState('')

  // Tesserae E-Ink preview state
  const [previewSize, setPreviewSize] = useState<'sm' | 'md' | 'lg'>('md')
  const [previewTheme, setPreviewTheme] = useState<'mono' | 'inverted'>('mono')
  const [syncing, setSyncing] = useState(false)

  const toggleSection = (key: SectionKey) => {
    setOpenSections((prev) => ({ ...prev, [key]: !prev[key] }))
  }

  const showMsg = (type: 'ok' | 'err', text: string) => {
    setFeedback({ type, text })
  }

  const load = async () => {
    try {
      const s = await api.getSettings()
      setStatus(s)
      setDemoMode(s.demo_mode)
      setSyncInterval(s.sync_interval_minutes)
      if (s.scoring_targets) {
        setScoringTargets(s.scoring_targets)
      }
      onDemoModeChange?.(s.demo_mode)
      setCountry((s.picnic_country_code === 'NL' ? 'NL' : 'DE') as 'DE' | 'NL')
      setTwoFaStep(s.picnic_2fa_pending)
      setMealieUrl(s.mealie_url || '')
      setLlmBaseUrl(s.llm_base_url || 'https://api.deepseek.com')
      setLlmModel(s.llm_model || 'deepseek-flash')
      setLlmUseResponses(s.llm_use_responses_api)
      setOidcEnabled(s.oidc_enabled)
      setOidcProviderName(s.oidc_provider_name || 'PocketID')
      setOidcIssuerUrl(s.oidc_issuer_url || '')
      setOidcClientId(s.oidc_client_id || '')
      setOidcAllowedEmails(s.oidc_allowed_emails || '')
      if (s.picnic_2fa_pending || s.picnic_status === 'reauth_required') {
        setOpenSections((prev) => ({ ...prev, picnic: true }))
      }
    } catch (err) {
      showMsg('err', err instanceof Error ? err.message : 'Einstellungen nicht ladbar')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const handleSaveApp = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const res = await api.saveAppSettings({
        demo_mode: demoMode,
        sync_interval_minutes: syncInterval,
        api_key: apiKeyInput.trim() || undefined,
        scoring_targets: scoringTargets,
      })
      setApiKeyInput('')
      showMsg('ok', res.message)
      await load()
    } catch (err) {
      showMsg('err', err instanceof Error ? err.message : 'Speichern fehlgeschlagen')
    }
  }

  const handleClearApiKey = async () => {
    try {
      await api.saveAppSettings({ clear_api_key: true })
      setApiKeyInput('')
      showMsg('ok', 'API-Key Schutz deaktiviert.')
      await load()
    } catch (err) {
      showMsg('err', err instanceof Error ? err.message : 'Deaktivieren fehlgeschlagen')
    }
  }

  const handleClearDemo = async () => {
    try {
      const res = await api.clearDemoData()
      showMsg('ok', res.message)
      await load()
    } catch (err) {
      showMsg('err', err instanceof Error ? err.message : 'Bereinigen fehlgeschlagen')
    }
  }

  const handlePicnicLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const res = await api.picnicLogin({ country_code: country, username, password })
      setPassword('')
      setTwoFaStep(res.status === '2fa_required')
      showMsg('ok', res.message)
      await load()
    } catch (err) {
      showMsg('err', err instanceof Error ? err.message : 'Picnic Login fehlgeschlagen')
    }
  }

  const handle2FAChannel = async (channel: 'SMS' | 'EMAIL') => {
    try {
      const res = await api.picnic2FAGenerate(channel)
      showMsg('ok', res.message)
    } catch (err) {
      showMsg('err', err instanceof Error ? err.message : '2FA-Code Versand fehlgeschlagen')
    }
  }

  const handle2FAVerify = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const res = await api.picnic2FAVerify(otpCode)
      setOtpCode('')
      setTwoFaStep(false)
      showMsg('ok', res.message)
      await load()
    } catch (err) {
      showMsg('err', err instanceof Error ? err.message : '2FA-Prüfung fehlgeschlagen')
    }
  }

  const handleDisconnect = async () => {
    try {
      const res = await api.picnicDisconnect()
      setTwoFaStep(false)
      showMsg('ok', res.message)
      await load()
    } catch (err) {
      showMsg('err', err instanceof Error ? err.message : 'Trennen fehlgeschlagen')
    }
  }

  const handleSaveMealie = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const res = await api.saveMealieSettings({
        mealie_url: mealieUrl,
        mealie_api_token: mealieToken || undefined,
      })
      setMealieToken('')
      showMsg('ok', res.message)
      await load()
    } catch (err) {
      showMsg('err', err instanceof Error ? err.message : 'Speichern fehlgeschlagen')
    }
  }

  const handleTestMealie = async () => {
    try {
      const res = await api.testMealie()
      showMsg('ok', `Mealie verbunden (${res.username ?? 'OK'})`)
    } catch (err) {
      showMsg('err', err instanceof Error ? err.message : 'Mealie-Test fehlgeschlagen')
    }
  }

  const handleSaveLLM = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const res = await api.saveLLMSettings({
        llm_base_url: llmBaseUrl,
        llm_api_key: llmApiKey || undefined,
        llm_model: llmModel,
        llm_use_responses_api: llmUseResponses,
      })
      setLlmApiKey('')
      showMsg('ok', res.message)
      await load()
    } catch (err) {
      showMsg('err', err instanceof Error ? err.message : 'Speichern fehlgeschlagen')
    }
  }

  const handleTestLLM = async () => {
    try {
      const res = await api.testLLM()
      showMsg('ok', `LLM OK (${res.model} → Test-Bucket: ${res.sample_bucket ?? 'ok'})`)
    } catch (err) {
      showMsg('err', err instanceof Error ? err.message : 'LLM-Test fehlgeschlagen')
    }
  }

  const handleSaveOIDC = async (e: React.FormEvent) => {
    e.preventDefault()
    const wasEnabled = Boolean(status?.oidc_enabled)
    try {
      const res = await api.saveOIDCSettings({
        enabled: oidcEnabled,
        issuer_url: oidcIssuerUrl.trim(),
        client_id: oidcClientId.trim(),
        client_secret: oidcClientSecret.trim() || undefined,
        allowed_emails: oidcAllowedEmails.trim(),
        provider_name: oidcProviderName.trim() || 'PocketID',
      })
      setOidcClientSecret('')
      if (!wasEnabled && oidcEnabled) {
        showMsg('ok', `${res.message} Weiterleitung zur Anmeldung…`)
        window.location.assign('/api/auth/oidc/login')
        return
      }
      showMsg('ok', res.message)
      await load()
    } catch (err) {
      showMsg('err', err instanceof Error ? err.message : 'OIDC-Speichern fehlgeschlagen')
    }
  }

  const handleClearOidcSecret = async () => {
    try {
      const res = await api.saveOIDCSettings({
        enabled: oidcEnabled,
        issuer_url: oidcIssuerUrl.trim(),
        client_id: oidcClientId.trim(),
        clear_client_secret: true,
        allowed_emails: oidcAllowedEmails.trim(),
        provider_name: oidcProviderName.trim() || 'PocketID',
      })
      setOidcClientSecret('')
      showMsg('ok', res.message)
      await load()
    } catch (err) {
      showMsg('err', err instanceof Error ? err.message : 'Entfernen fehlgeschlagen')
    }
  }

  const handleTestOIDC = async () => {
    try {
      const res = await api.testOIDC()
      showMsg('ok', `OIDC Discovery OK (${res.issuer ?? oidcIssuerUrl})`)
    } catch (err) {
      showMsg('err', err instanceof Error ? err.message : 'OIDC-Test fehlgeschlagen')
    }
  }

  const handleManualSync = async () => {
    setSyncing(true)
    try {
      await api.triggerSync()
      showMsg('ok', 'Synchronisation & Anreicherung erfolgreich abgeschlossen.')
      await load()
    } catch (err) {
      showMsg('err', err instanceof Error ? err.message : 'Sync fehlgeschlagen')
    } finally {
      setSyncing(false)
    }
  }

  const origin = typeof window !== 'undefined' ? window.location.origin : ''
  const summaryUrl = `${origin}/api/v1/summary`
  const einkUrl = `${origin}/widget/eink?size=${previewSize}&theme=${previewTheme}`
  const oidcCallbackUrl = `${origin}/api/auth/oidc/callback`

  const copyText = (text: string, label = 'URL') => {
    void navigator.clipboard?.writeText(text)
    showMsg('ok', `${label} in die Zwischenablage kopiert.`)
  }

  if (loading || !status) {
    return <div className="p-6 text-sm text-zinc-400">Lade Einstellungen…</div>
  }

  const previewWidth = previewSize === 'sm' ? 230 : previewSize === 'md' ? 320 : 440
  const previewHeight = previewSize === 'sm' ? 165 : previewSize === 'md' ? 235 : 275

  const picnicBadge =
    status.picnic_status === 'ok'
      ? 'Verbunden'
      : status.picnic_status === 'demo'
        ? 'Demo-Daten'
        : status.picnic_status === 'reauth_required'
          ? 'Neu anmelden'
          : status.picnic_status === '2fa_pending'
            ? '2FA offen'
            : 'Nicht verbunden'
  const picnicTone: 'sage' | 'amber' | 'neutral' =
    status.picnic_status === 'ok' || status.picnic_status === 'demo'
      ? 'sage'
      : status.picnic_status === 'reauth_required' || status.picnic_status === '2fa_pending'
        ? 'amber'
        : 'neutral'

  return (
    <div className="space-y-4">
      {feedback && (
        <div
          className={`rounded-2xl p-3.5 text-sm border ${
            feedback.type === 'ok'
              ? 'bg-[#2E7D5B]/10 border-[#2E7D5B]/25 text-[#1F5A41]'
              : 'bg-[#D97706]/10 border-[#D97706]/30 text-[#92400E]'
          }`}
        >
          {feedback.text}
        </div>
      )}

      {/* Sync & Status Header */}
      <section className="bg-white border border-[#E5E4DF] rounded-2xl p-4 sm:p-5 flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-base font-semibold text-[#18181B]">Einstellungen & Sync</h2>
            {status.demo_mode && (
              <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-[#2E7D5B]/10 text-[#2E7D5B]">
                DEMO
              </span>
            )}
          </div>
          <p className="text-xs text-zinc-500 mt-0.5">
            Sync:{' '}
            {status.sync_interval_minutes > 0 ? `alle ${status.sync_interval_minutes} Min.` : 'Aus'}{' '}
            · API-Key: {status.api_key_enabled ? 'Aktiv' : 'Aus'} · Speicher:{' '}
            <code className="font-mono">{status.app_data_dir}</code>
          </p>
        </div>

        <button
          type="button"
          disabled={syncing}
          onClick={handleManualSync}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-[#18181B] hover:bg-zinc-800 text-white text-sm font-medium transition cursor-pointer disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${syncing ? 'animate-spin' : ''}`} />
          {syncing ? 'Synchronisiert…' : 'Jetzt synchronisieren'}
        </button>
      </section>

      {/* 1) Picnic 2FA Setup */}
      <CollapsibleCard
        icon={<KeyRound className="w-4 h-4" />}
        title="Picnic Konto & 2FA"
        subtitle="Interaktiver Login mit verschlüsseltem Session-Token"
        badge={picnicBadge}
        badgeTone={picnicTone}
        open={openSections.picnic}
        onToggle={() => toggleSection('picnic')}
      >
        <div className="pt-3 space-y-4">
          {status.demo_mode ? (
            <p className="text-xs text-zinc-500 leading-relaxed bg-[#FAF9F6] border border-[#E5E4DF] rounded-xl p-3.5">
              Die App läuft aktuell im Demo-Modus. Deaktiviere unten unter{' '}
              <strong>App-Einstellungen</strong> den Demo-Modus, um dein echtes Picnic-Konto per 2FA
              zu verbinden.
            </p>
          ) : (
            <>
              {status.picnic_has_token && (
                <div className="flex items-center justify-between gap-2 p-3 rounded-xl bg-[#FAF9F6] border border-[#E5E4DF] text-xs">
                  <div className="flex items-center gap-2 text-zinc-700">
                    <CheckCircle2 className="w-4 h-4 text-[#2E7D5B]" />
                    <span>
                      Sitzung gespeichert ({status.picnic_country_code} ·{' '}
                      {status.picnic_username_masked || 'Konto'})
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={handleDisconnect}
                    className="inline-flex items-center gap-1 text-zinc-500 hover:text-red-600 cursor-pointer"
                  >
                    <Unplug className="w-3.5 h-3.5" />
                    Trennen
                  </button>
                </div>
              )}

              <form onSubmit={handlePicnicLogin} className="space-y-3 max-w-md">
                <div className="grid grid-cols-3 gap-2">
                  <select
                    value={country}
                    onChange={(e) => setCountry(e.target.value as 'DE' | 'NL')}
                    className="px-3 py-2 text-sm rounded-xl border border-[#E5E4DF] bg-[#FAF9F6]"
                  >
                    <option value="DE">DE</option>
                    <option value="NL">NL</option>
                  </select>
                  <input
                    type="email"
                    required
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    placeholder="Picnic E-Mail"
                    className="col-span-2 px-3 py-2 text-sm rounded-xl border border-[#E5E4DF] bg-[#FAF9F6] focus:bg-white focus:outline-none"
                  />
                </div>
                <input
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Picnic Passwort (wird nicht gespeichert)"
                  className="w-full px-3 py-2 text-sm rounded-xl border border-[#E5E4DF] bg-[#FAF9F6] focus:bg-white focus:outline-none"
                />
                <button
                  type="submit"
                  className="w-full py-2 rounded-xl bg-[#18181B] hover:bg-zinc-800 text-white text-sm font-medium cursor-pointer"
                >
                  Schritt 1: Anmeldung starten
                </button>
              </form>

              {twoFaStep && (
                <div className="pt-3 border-t border-[#ECEBE6] space-y-3 max-w-md">
                  <div className="text-xs font-medium text-zinc-700">
                    Schritt 2: 2FA-Bestätigungscode anfordern & eingeben
                  </div>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => handle2FAChannel('SMS')}
                      className="flex-1 py-1.5 rounded-xl border border-[#E5E4DF] bg-[#FAF9F6] hover:bg-zinc-100 text-xs font-medium cursor-pointer"
                    >
                      Code per SMS senden
                    </button>
                    <button
                      type="button"
                      onClick={() => handle2FAChannel('EMAIL')}
                      className="flex-1 py-1.5 rounded-xl border border-[#E5E4DF] bg-[#FAF9F6] hover:bg-zinc-100 text-xs font-medium cursor-pointer"
                    >
                      Code per E-Mail senden
                    </button>
                  </div>
                  <form onSubmit={handle2FAVerify} className="flex gap-2">
                    <input
                      type="text"
                      required
                      value={otpCode}
                      onChange={(e) => setOtpCode(e.target.value)}
                      placeholder="6-stelliger Code"
                      className="flex-1 px-3 py-2 text-sm rounded-xl border border-[#E5E4DF] bg-[#FAF9F6] tabular-nums"
                    />
                    <button
                      type="submit"
                      className="px-4 py-2 rounded-xl bg-[#2E7D5B] text-white text-sm font-medium cursor-pointer"
                    >
                      Bestätigen
                    </button>
                  </form>
                </div>
              )}
            </>
          )}
        </div>
      </CollapsibleCard>

      {/* 2) App-Einstellungen */}
      <CollapsibleCard
        icon={<Sliders className="w-4 h-4" />}
        title="App-Einstellungen"
        subtitle="Demo-Modus, Sync-Intervall & API-Key"
        badge={status.demo_mode ? 'Demo aktiv' : 'Live-Betrieb'}
        badgeTone={status.demo_mode ? 'sage' : 'neutral'}
        open={openSections.app}
        onToggle={() => toggleSection('app')}
      >
        <form onSubmit={handleSaveApp} className="pt-3 grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
          <div className="p-3 rounded-xl bg-[#FAF9F6] border border-[#E5E4DF] space-y-1.5">
            <label className="flex items-center justify-between gap-2 text-xs font-medium text-[#18181B] cursor-pointer">
              <span>Demo-Modus</span>
              <input
                type="checkbox"
                checked={demoMode}
                onChange={(e) => setDemoMode(e.target.checked)}
                className="w-4 h-4 accent-[#2E7D5B] cursor-pointer"
              />
            </label>
            <p className="text-[11px] text-zinc-500">
              An zum Ausprobieren mit Beispieldaten, Aus für dein echtes Picnic-Konto.
            </p>
          </div>

          <div className="space-y-1">
            <label className="block text-xs font-medium text-zinc-600">
              Automatisches Sync-Intervall
            </label>
            <select
              value={syncInterval}
              onChange={(e) => setSyncInterval(Number(e.target.value))}
              className="w-full px-3 py-2 text-sm rounded-xl border border-[#E5E4DF] bg-[#FAF9F6]"
            >
              <option value={0}>Deaktiviert (nur manuell)</option>
              <option value={15}>Alle 15 Minuten</option>
              <option value={30}>Alle 30 Minuten</option>
              <option value={60}>Alle 60 Minuten (Standard)</option>
              <option value={120}>Alle 2 Stunden</option>
              <option value={360}>Alle 6 Stunden</option>
            </select>
          </div>

          <div className="space-y-1">
            <label className="block text-xs font-medium text-zinc-600">
              API-Key (Tesserae / Home Assistant)
            </label>
            <div className="flex gap-1.5">
              <input
                type="text"
                value={apiKeyInput}
                onChange={(e) => setApiKeyInput(e.target.value)}
                placeholder={
                  status.api_key_enabled
                    ? `Aktiv (${status.api_key_masked})`
                    : 'Optionaler Zugriffsschlüssel'
                }
                className="min-w-0 flex-1 px-3 py-2 text-sm rounded-xl border border-[#E5E4DF] bg-[#FAF9F6] font-mono"
              />
              <button
                type="button"
                onClick={() => {
                  const k = generateRandomApiKey()
                  setApiKeyInput(k)
                  copyText(k, 'Neuer API-Key')
                }}
                title="Zufälligen API-Key generieren & kopieren"
                className="px-2.5 py-2 rounded-xl border border-[#E5E4DF] bg-[#FAF9F6] hover:bg-zinc-100 text-zinc-700 cursor-pointer"
              >
                <Wand2 className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Persönliche Scoring-Ziele */}
          <div className="md:col-span-3 pt-3 border-t border-[#ECEBE6] space-y-2.5">
            <div className="text-xs font-semibold text-zinc-700">
              Persönliche Scoring-Ziele (für Score & 4 Ziel-Häkchen)
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <label className="space-y-1 text-xs text-zinc-600">
                <span>Protein (g / 1.000 kcal)</span>
                <input
                  type="number"
                  min={15}
                  max={80}
                  step={1}
                  value={scoringTargets.protein_per_1000_kcal}
                  onChange={(e) =>
                    setScoringTargets((prev) => ({
                      ...prev,
                      protein_per_1000_kcal: Number(e.target.value),
                    }))
                  }
                  className="w-full px-3 py-1.5 text-sm rounded-xl border border-[#E5E4DF] bg-[#FAF9F6] tabular-nums"
                />
              </label>
              <label className="space-y-1 text-xs text-zinc-600">
                <span>Frisch & Gemüse (%)</span>
                <input
                  type="number"
                  min={10}
                  max={70}
                  step={1}
                  value={scoringTargets.fresh_share_pct}
                  onChange={(e) =>
                    setScoringTargets((prev) => ({
                      ...prev,
                      fresh_share_pct: Number(e.target.value),
                    }))
                  }
                  className="w-full px-3 py-1.5 text-sm rounded-xl border border-[#E5E4DF] bg-[#FAF9F6] tabular-nums"
                />
              </label>
              <label className="space-y-1 text-xs text-zinc-600">
                <span>NOVA 1–2 (%)</span>
                <input
                  type="number"
                  min={40}
                  max={95}
                  step={1}
                  value={scoringTargets.nova_1_2_share_pct}
                  onChange={(e) =>
                    setScoringTargets((prev) => ({
                      ...prev,
                      nova_1_2_share_pct: Number(e.target.value),
                    }))
                  }
                  className="w-full px-3 py-1.5 text-sm rounded-xl border border-[#E5E4DF] bg-[#FAF9F6] tabular-nums"
                />
              </label>
              <label className="space-y-1 text-xs text-zinc-600">
                <span>Max. Snacks (%)</span>
                <input
                  type="number"
                  min={0}
                  max={40}
                  step={1}
                  value={scoringTargets.snack_share_pct}
                  onChange={(e) =>
                    setScoringTargets((prev) => ({
                      ...prev,
                      snack_share_pct: Number(e.target.value),
                    }))
                  }
                  className="w-full px-3 py-1.5 text-sm rounded-xl border border-[#E5E4DF] bg-[#FAF9F6] tabular-nums"
                />
              </label>
            </div>
          </div>

          <div className="md:col-span-3 flex flex-wrap items-center justify-between gap-2 pt-1">
            <div className="flex flex-wrap items-center gap-2">
              <a
                href="/api/v1/settings/backup"
                download
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-[#E5E4DF] bg-[#FAF9F6] hover:bg-zinc-100 text-xs font-medium text-zinc-700"
              >
                <Download className="w-3.5 h-3.5" />
                DB-Backup (.db)
              </a>
              {!status.demo_mode && (
                <button
                  type="button"
                  onClick={handleClearDemo}
                  className="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl border border-[#E5E4DF] bg-[#FAF9F6] hover:bg-zinc-100 text-xs font-medium text-zinc-600 cursor-pointer"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  Demo-Daten bereinigen
                </button>
              )}
            </div>
            <div className="flex items-center gap-2">
              {status.api_key_enabled && (
                <button
                  type="button"
                  onClick={handleClearApiKey}
                  className="px-3 py-2 rounded-xl border border-[#E5E4DF] bg-[#FAF9F6] hover:bg-zinc-100 text-xs font-medium text-zinc-600 cursor-pointer"
                >
                  API-Key entfernen
                </button>
              )}
              <button
                type="submit"
                className="px-4 py-2 rounded-xl bg-[#18181B] hover:bg-zinc-800 text-white text-sm font-medium cursor-pointer"
              >
                Speichern
              </button>
            </div>
          </div>
        </form>
      </CollapsibleCard>

      {/* 3) Zugriffsschutz (OIDC / PocketID) */}
      <CollapsibleCard
        icon={<ShieldCheck className="w-4 h-4" />}
        title="Zugriffsschutz (OIDC / PocketID)"
        subtitle="Haushalts-Login per Passkey/SSO · E-Ink & Home Assistant bleiben per API-Key erreichbar"
        badge={status.oidc_enabled ? `Aktiv (${status.oidc_provider_name})` : 'Optional'}
        badgeTone={status.oidc_enabled ? 'sage' : 'neutral'}
        open={openSections.oidc}
        onToggle={() => toggleSection('oidc')}
      >
        <form onSubmit={handleSaveOIDC} className="pt-3 space-y-3 max-w-2xl">
          <div className="p-3 rounded-xl bg-[#FAF9F6] border border-[#E5E4DF] space-y-1.5">
            <div className="text-[11px] font-medium text-zinc-500">
              Redirect / Callback URL (in PocketID als Callback URL hinterlegen)
            </div>
            <div className="flex items-center justify-between gap-2">
              <code className="text-xs font-mono text-zinc-700 truncate">{oidcCallbackUrl}</code>
              <button
                type="button"
                onClick={() => copyText(oidcCallbackUrl, 'Callback URL')}
                className="shrink-0 inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-white border border-[#E5E4DF] text-xs text-zinc-700 hover:bg-zinc-50 cursor-pointer"
              >
                <Copy className="w-3 h-3" />
                Kopieren
              </button>
            </div>
          </div>

          <div className="p-3 rounded-xl bg-[#FAF9F6] border border-[#E5E4DF] flex items-center justify-between gap-3">
            <div>
              <div className="text-xs font-medium text-[#18181B]">OIDC-Anmeldung erzwingen</div>
              <p className="text-[11px] text-zinc-500">
                Schützt alle Web-UI-Ansichten (30-Tage-Cookie). Vor Aktivierung prüft das Backend
                automatisch die Discovery-URL.
              </p>
            </div>
            <input
              type="checkbox"
              checked={oidcEnabled}
              onChange={(e) => setOidcEnabled(e.target.checked)}
              className="w-4 h-4 accent-[#2E7D5B] cursor-pointer shrink-0"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
            <label className="space-y-1 text-xs text-zinc-600">
              <span>Anzeigename (Login-Button)</span>
              <input
                type="text"
                value={oidcProviderName}
                onChange={(e) => setOidcProviderName(e.target.value)}
                placeholder="PocketID"
                className="w-full px-3 py-2 text-sm rounded-xl border border-[#E5E4DF] bg-[#FAF9F6]"
              />
            </label>
            <label className="space-y-1 text-xs text-zinc-600">
              <span>Issuer URL</span>
              <input
                type="url"
                value={oidcIssuerUrl}
                onChange={(e) => setOidcIssuerUrl(e.target.value)}
                placeholder="https://id.deinedomain.de"
                className="w-full px-3 py-2 text-sm rounded-xl border border-[#E5E4DF] bg-[#FAF9F6]"
              />
            </label>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
            <label className="space-y-1 text-xs text-zinc-600">
              <span>Client ID</span>
              <input
                type="text"
                value={oidcClientId}
                onChange={(e) => setOidcClientId(e.target.value)}
                placeholder="Aus PocketID kopieren"
                className="w-full px-3 py-2 text-sm rounded-xl border border-[#E5E4DF] bg-[#FAF9F6] font-mono"
              />
            </label>
            <label className="space-y-1 text-xs text-zinc-600">
              <span>Client Secret (optional bei PKCE Public Client)</span>
              <input
                type="password"
                value={oidcClientSecret}
                onChange={(e) => setOidcClientSecret(e.target.value)}
                placeholder={
                  status.oidc_has_secret
                    ? 'Gespeichert (leer lassen zum Behalten)'
                    : 'Leer lassen bei Public Client'
                }
                className="w-full px-3 py-2 text-sm rounded-xl border border-[#E5E4DF] bg-[#FAF9F6]"
              />
            </label>
          </div>

          <label className="block space-y-1 text-xs text-zinc-600">
            <span>Erlaubte E-Mail-Adressen (optional, kommagetrennt)</span>
            <input
              type="text"
              value={oidcAllowedEmails}
              onChange={(e) => setOidcAllowedEmails(e.target.value)}
              placeholder="du@example.de, partner@example.de (leer = alle im PocketID-Client)"
              className="w-full px-3 py-2 text-sm rounded-xl border border-[#E5E4DF] bg-[#FAF9F6]"
            />
          </label>

          <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
            <div>
              {status.oidc_has_secret && (
                <button
                  type="button"
                  onClick={handleClearOidcSecret}
                  className="px-3 py-2 rounded-xl border border-[#E5E4DF] bg-[#FAF9F6] hover:bg-zinc-100 text-xs font-medium text-zinc-600 cursor-pointer"
                >
                  Client Secret entfernen
                </button>
              )}
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleTestOIDC}
                className="px-4 py-2 rounded-xl border border-[#E5E4DF] bg-[#FAF9F6] hover:bg-zinc-100 text-sm font-medium text-zinc-700 cursor-pointer"
              >
                Discovery testen
              </button>
              <button
                type="submit"
                className="px-4 py-2 rounded-xl bg-[#18181B] hover:bg-zinc-800 text-white text-sm font-medium cursor-pointer"
              >
                Speichern
              </button>
            </div>
          </div>
        </form>
      </CollapsibleCard>

      {/* 4) DeepSeek / LLM Config */}
      <CollapsibleCard
        icon={<Sparkles className="w-4 h-4" />}
        title="LLM Anreicherung (DeepSeek Flash)"
        subtitle="Fallback wenn OpenFoodFacts keinen Treffer hat"
        badge={status.llm_configured ? `Aktiv (${status.llm_api_key_masked})` : 'Optional'}
        badgeTone={status.llm_configured ? 'sage' : 'neutral'}
        open={openSections.llm}
        onToggle={() => toggleSection('llm')}
      >
        <form onSubmit={handleSaveLLM} className="pt-3 space-y-3 max-w-xl">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <input
              type="url"
              value={llmBaseUrl}
              onChange={(e) => setLlmBaseUrl(e.target.value)}
              placeholder="https://api.deepseek.com"
              className="px-3 py-2 text-sm rounded-xl border border-[#E5E4DF] bg-[#FAF9F6]"
            />
            <input
              type="text"
              value={llmModel}
              onChange={(e) => setLlmModel(e.target.value)}
              placeholder="deepseek-flash"
              className="px-3 py-2 text-sm rounded-xl border border-[#E5E4DF] bg-[#FAF9F6]"
            />
          </div>

          <input
            type="password"
            value={llmApiKey}
            onChange={(e) => setLlmApiKey(e.target.value)}
            placeholder={
              status.llm_api_key_masked
                ? `Neuer API-Key (aktuell: ${status.llm_api_key_masked})`
                : 'LLM API-Key eingeben'
            }
            className="w-full px-3 py-2 text-sm rounded-xl border border-[#E5E4DF] bg-[#FAF9F6]"
          />

          <label className="flex items-center gap-2 text-xs text-zinc-600 cursor-pointer">
            <input
              type="checkbox"
              checked={llmUseResponses}
              onChange={(e) => setLlmUseResponses(e.target.checked)}
              className="rounded border-zinc-300"
            />
            DeepSeek Responses API (<code className="font-mono">json_schema</code>) nutzen
          </label>

          <div className="flex gap-2">
            <button
              type="submit"
              className="flex-1 py-2 rounded-xl bg-[#18181B] hover:bg-zinc-800 text-white text-sm font-medium cursor-pointer"
            >
              Speichern
            </button>
            <button
              type="button"
              onClick={handleTestLLM}
              className="px-4 py-2 rounded-xl border border-[#E5E4DF] bg-[#FAF9F6] hover:bg-zinc-100 text-sm font-medium text-zinc-700 cursor-pointer"
            >
              Testen
            </button>
          </div>
        </form>
      </CollapsibleCard>

      {/* 4) Optional Read-Only Mealie */}
      <CollapsibleCard
        icon={<Utensils className="w-4 h-4" />}
        title="Mealie Integration (Read-Only)"
        subtitle="Wochen-Rezepte mit Fotos & Health-Scores"
        badge={status.mealie_configured ? 'Aktiv' : 'Optional'}
        badgeTone={status.mealie_configured ? 'sage' : 'neutral'}
        open={openSections.mealie}
        onToggle={() => toggleSection('mealie')}
      >
        <form onSubmit={handleSaveMealie} className="pt-3 space-y-3 max-w-xl">
          <input
            type="url"
            value={mealieUrl}
            onChange={(e) => setMealieUrl(e.target.value)}
            placeholder="https://mealie.example.com"
            className="w-full px-3 py-2 text-sm rounded-xl border border-[#E5E4DF] bg-[#FAF9F6]"
          />
          <input
            type="password"
            value={mealieToken}
            onChange={(e) => setMealieToken(e.target.value)}
            placeholder={
              status.mealie_token_masked
                ? `Neuer API-Token (aktuell: ${status.mealie_token_masked})`
                : 'Mealie Long-Lived API Token'
            }
            className="w-full px-3 py-2 text-sm rounded-xl border border-[#E5E4DF] bg-[#FAF9F6]"
          />
          <div className="flex gap-2">
            <button
              type="submit"
              className="flex-1 py-2 rounded-xl bg-[#18181B] hover:bg-zinc-800 text-white text-sm font-medium cursor-pointer"
            >
              Speichern
            </button>
            <button
              type="button"
              onClick={handleTestMealie}
              className="px-4 py-2 rounded-xl border border-[#E5E4DF] bg-[#FAF9F6] hover:bg-zinc-100 text-sm font-medium text-zinc-700 cursor-pointer"
            >
              Testen
            </button>
          </div>
        </form>
      </CollapsibleCard>

      {/* 5) Tesserae & E-Ink Widget Preview */}
      <CollapsibleCard
        icon={<Monitor className="w-4 h-4" />}
        title="Tesserae E-Ink & Home Assistant"
        subtitle="JSON-Endpunkt & Live-Vorschau für E-Paper"
        badge={status.api_key_enabled ? 'Geschützt' : 'Bereit'}
        badgeTone="sage"
        open={openSections.tesserae}
        onToggle={() => toggleSection('tesserae')}
      >
        <div className="pt-3 space-y-4">
          <div className="space-y-2 text-xs">
            <div className="flex items-center justify-between gap-2 p-2.5 rounded-xl bg-[#FAF9F6] border border-[#E5E4DF]">
              <code className="truncate text-zinc-700">{summaryUrl}</code>
              <button
                type="button"
                onClick={() => copyText(summaryUrl)}
                className="shrink-0 inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-white border border-[#E5E4DF] text-zinc-600 cursor-pointer"
              >
                <Copy className="w-3 h-3" />
                JSON
              </button>
            </div>
            <div className="flex items-center justify-between gap-2 p-2.5 rounded-xl bg-[#FAF9F6] border border-[#E5E4DF]">
              <code className="truncate text-zinc-700">{einkUrl}</code>
              <button
                type="button"
                onClick={() => copyText(einkUrl)}
                className="shrink-0 inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-white border border-[#E5E4DF] text-zinc-600 cursor-pointer"
              >
                <Copy className="w-3 h-3" />
                E-Ink
              </button>
            </div>
          </div>

          <div className="flex items-center justify-between gap-2 flex-wrap">
            <div className="flex gap-1">
              {(['sm', 'md', 'lg'] as const).map((sz) => (
                <button
                  key={sz}
                  type="button"
                  onClick={() => setPreviewSize(sz)}
                  className={`px-2.5 py-1 rounded-lg text-xs font-medium border cursor-pointer ${
                    previewSize === sz
                      ? 'bg-[#18181B] text-white border-[#18181B]'
                      : 'bg-[#FAF9F6] text-zinc-600 border-[#E5E4DF]'
                  }`}
                >
                  {sz.toUpperCase()}
                </button>
              ))}
            </div>
            <div className="flex gap-1">
              {(['mono', 'inverted'] as const).map((th) => (
                <button
                  key={th}
                  type="button"
                  onClick={() => setPreviewTheme(th)}
                  className={`px-2.5 py-1 rounded-lg text-xs font-medium border cursor-pointer ${
                    previewTheme === th
                      ? 'bg-[#18181B] text-white border-[#18181B]'
                      : 'bg-[#FAF9F6] text-zinc-600 border-[#E5E4DF]'
                  }`}
                >
                  {th === 'mono' ? 'Papier' : 'Invertiert'}
                </button>
              ))}
            </div>
          </div>

          {status.api_key_enabled ? (
            <p className="text-xs text-zinc-500">
              API-Key aktiv: Im Tesserae Web-Widget bitte{' '}
              <code className="font-mono">X-API-Key</code> oder{' '}
              <code className="font-mono">Authorization: Bearer</code> setzen.
            </p>
          ) : (
            <div className="overflow-x-auto flex justify-center py-2 bg-[#F2F0EA] rounded-xl border border-[#E5E4DF]">
              <iframe
                title="Tesserae E-Ink Vorschau"
                src={`/widget/eink?size=${previewSize}&theme=${previewTheme}`}
                style={{ width: previewWidth, height: previewHeight }}
                className="border-0 bg-transparent"
              />
            </div>
          )}
        </div>
      </CollapsibleCard>

      {/* Recent Sync Runs */}
      {status.recent_sync_runs.length > 0 && (
        <section className="bg-white border border-[#E5E4DF] rounded-2xl p-4 sm:p-5">
          <h3 className="text-sm font-semibold text-[#18181B] mb-2.5">Letzte Sync-Läufe</h3>
          <div className="divide-y divide-[#ECEBE6] text-xs">
            {status.recent_sync_runs.map((run) => (
              <div key={run.id} className="py-2 flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <span className="font-semibold uppercase text-zinc-700">{run.source}</span>
                  <span className="ml-2 text-zinc-500">
                    {run.summary || run.error || run.status}
                  </span>
                </div>
                <span
                  className={`shrink-0 px-2 py-0.5 rounded-full font-medium ${
                    run.status === 'ok'
                      ? 'bg-[#2E7D5B]/10 text-[#2E7D5B]'
                      : 'bg-[#D97706]/12 text-[#B45309]'
                  }`}
                >
                  {run.status}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
