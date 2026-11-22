import React, { useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { Icon, type IconName } from './Icon'
import { AIReviewPanel, Badge, CandidateJournal, Empty, HorizonCards, SetupPanel, SnapshotPanel } from './MarketViews'
import ResearchView from './ResearchView'
import SystemView from './SystemView'
import { isSweep, label, lifecycle, when } from './format'
import { useNow, useResource } from './hooks'
import type { Asset, CandidateEntry, Engine, Health, Snapshot, Timezone, View } from './types'
import './styles.css'

const navigation: { id: View; title: string; icon: IconName; subtitle: string }[] = [
  { id: 'overview', title: 'Overview', icon: 'grid', subtitle: 'Gold and Bitcoin. Three horizons. One clear view.' },
  { id: 'sweeps', title: 'Liquidity sweeps', icon: 'sweep', subtitle: 'Closed-candle sweep and reclaim candidates, with recorded evidence.' },
  { id: 'ai', title: 'AI reviews', icon: 'spark', subtitle: 'Independent assessments. Transparent reasoning. Deterministic checks.' },
  { id: 'research', title: 'Research', icon: 'research', subtitle: 'Trace every experiment back to its dataset and evidence.' },
  { id: 'system', title: 'System health', icon: 'pulse', subtitle: 'Connections, source observations and resource usage.' },
]

function viewFromHash(): View {
  const value = window.location.hash.replace('#', '')
  return navigation.find(row => row.id === value)?.id ?? 'overview'
}

function App() {
  const [view, setView] = useState<View>(viewFromHash)
  const [asset, setAsset] = useState<Asset>('GOLD')
  const [timezone, setTimezone] = useState<Timezone>('Asia/Kolkata')
  const [horizon, setHorizon] = useState<number | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [refresh, setRefresh] = useState(0)
  const [mobileOpen, setMobileOpen] = useState(false)
  const menuButton = useRef<HTMLButtonElement>(null)
  const sidebar = useRef<HTMLElement>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const now = useNow()
  const health = useResource<Health>('/api/health', refresh, true)
  const engines = useResource<Engine[]>('/api/engines', refresh, true)
  const candidates = useResource<CandidateEntry[]>('/api/candidates?limit=50&offset=0', refresh, true)
  const rows = Array.isArray(candidates.data) ? candidates.data : []
  const engineRows = Array.isArray(engines.data) ? engines.data : []
  const filtered = rows.filter(row => row.candidate.asset === asset
    && (horizon === null || row.candidate.horizon_minutes === horizon)
    && (view !== 'sweeps' || isSweep(row))
    && (row.candidate.trigger + ' ' + row.candidate.symbol + ' ' + row.candidate.engine + ' ' + row.candidate.direction).toLowerCase().includes(query.toLowerCase()))
  const selected = filtered.find(row => row.candidate.candidate_id === selectedId) ?? filtered[0] ?? null
  const snapshotRead = useResource<Snapshot>(selected ? '/api/snapshots/' + encodeURIComponent(selected.candidate.snapshot_id) : null, refresh)
  const matches = snapshotRead.data && selected
    && snapshotRead.data.snapshot_id === selected.candidate.snapshot_id
    && snapshotRead.data.symbol === selected.candidate.symbol
    && snapshotRead.data.asset === selected.candidate.asset
    && snapshotRead.data.engine === selected.candidate.engine
  const snapshot = matches ? snapshotRead.data : null
  const snapshotError = snapshotRead.error || (snapshotRead.data && !matches ? 'The returned snapshot does not match the selected candidate. Its values have been withheld.' : null)
  const title = navigation.find(row => row.id === view) ?? navigation[0]
  const marketView = view === 'overview' || view === 'sweeps' || view === 'ai'
  const refreshing = health.loading || engines.loading || candidates.loading
  const apiRecent = health.receivedAt !== null && now - health.receivedAt < 45_000 && !health.error
  const marketError = candidates.error || engines.error
  const scopeError = health.error || (marketView ? marketError : null)
  const date = new Intl.DateTimeFormat('en-GB', { weekday: 'short', day: 'numeric', month: 'short', timeZone: timezone }).format(new Date(now))

  useEffect(() => {
    const onHash = () => { setView(viewFromHash()); setMobileOpen(false) }
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])
  useEffect(() => {
    if (!mobileOpen) return
    const priorOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    sidebar.current?.querySelector<HTMLButtonElement>('button[aria-current="page"]')?.focus()
    const close = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { setMobileOpen(false); menuButton.current?.focus() }
    }
    const resize = () => { if (window.innerWidth > 1000) setMobileOpen(false) }
    window.addEventListener('keydown', close)
    window.addEventListener('resize', resize)
    return () => {
      document.body.style.overflow = priorOverflow
      window.removeEventListener('keydown', close)
      window.removeEventListener('resize', resize)
    }
  }, [mobileOpen])

  const navigate = (next: View) => {
    setView(next); setMobileOpen(false); setQuery(''); setHorizon(null)
    window.location.hash = next
    window.requestAnimationFrame(() => heading.current?.focus())
  }
  const chooseAsset = (next: Asset) => { setAsset(next); setSelectedId(null); setQuery(''); setHorizon(null) }
  const chooseEntry = (entry: CandidateEntry) => {
    setSelectedId(entry.candidate.candidate_id)
    if (view !== 'ai') document.getElementById('selected-evidence')?.scrollIntoView({ block: 'start', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' })
  }

  return <div className="app-shell">
    <a className="skip-link" href="#workspace-content" onClick={event => {
      event.preventDefault()
      document.getElementById('workspace-content')?.focus()
    }}>Skip to workspace</a>
    {mobileOpen && <button className="nav-backdrop" onClick={() => { setMobileOpen(false); menuButton.current?.focus() }} aria-label="Close navigation"/>}
    <aside className={'sidebar ' + (mobileOpen ? 'is-open' : '')} ref={sidebar} onKeyDown={event => {
      if (!mobileOpen || event.key !== 'Tab') return
      const focusable = sidebar.current?.querySelectorAll<HTMLButtonElement | HTMLAnchorElement>('button, a[href]')
      if (!focusable?.length) return
      const first = focusable[0], last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }}>
      <div className="brand"><span className="brand-symbol"><svg viewBox="0 0 32 32" aria-hidden="true"><path d="M4 7h7l5 10 5-10h7L16 29z" fill="currentColor"/><path d="m12 4 4 8 4-8z" fill="#87d6c5"/></svg></span><div>VECTOR<span>MARKET INTELLIGENCE</span></div><button className="mobile-close icon-button" onClick={() => { setMobileOpen(false); menuButton.current?.focus() }} aria-label="Close navigation"><Icon name="close"/></button></div>
      <div className="workspace-label"><span className="workspace-avatar">RD</span><div>Research workspace<small>Gold & Bitcoin</small></div><span className="workspace-lock"><Icon name="shield" size={16}/></span></div>
      <div className="nav-caption">WORKSPACE</div>
      <nav aria-label="Main navigation">{navigation.map(item => <button key={item.id} data-testid={'nav-' + item.id} className={'nav-item ' + (view === item.id ? 'active' : '')} aria-current={view === item.id ? 'page' : undefined} onClick={() => navigate(item.id)}><Icon name={item.icon}/><span>{item.title}</span>{view === item.id && <span className="nav-indicator"/>}</button>)}</nav>
      <div className="sidebar-bottom"><div className="workspace-note"><Icon name="shield" size={19}/><strong>Built for observation</strong><p>Research signals and evidence.<br/>No order execution.</p></div><a href="https://github.com/Rameshdandu1/gold_bitcoin#readme" target="_blank" rel="noreferrer">Documentation <Icon name="external" size={14}/></a><div className="sidebar-version"><span className="online-dot"/>Operator dashboard<span>v0.6</span></div></div>
    </aside>
    <div className="main-shell" inert={mobileOpen}>
      <header className="topbar"><div className="breadcrumb"><button className="mobile-menu icon-button" ref={menuButton} onClick={() => setMobileOpen(true)} aria-label="Open navigation" aria-expanded={mobileOpen}><Icon name="menu"/></button><span>Workspace</span><Icon name="chevron" size={12}/><strong>{title.title}</strong></div><div className="topbar-tools"><span className="research-mode"><Icon name="shield" size={13}/> Research only</span><span className="topbar-divider"/><label className="timezone-label"><Icon name="clock" size={14}/><span className="sr-only">Display timezone</span><select value={timezone} onChange={event => setTimezone(event.target.value as Timezone)} aria-label="Display timezone"><option value="Asia/Kolkata">IST · UTC+5:30</option><option value="UTC">UTC</option></select></label><span className="profile-avatar" aria-label="Operator workspace">RD</span></div></header>
      <main id="workspace-content" className="workspace-content" tabIndex={-1}>
        <div className="page-heading"><div><p className="eyebrow">YOUR RESEARCH WORKSPACE <span> / {date}</span></p><h1 ref={heading} tabIndex={-1}>{title.title === 'Overview' ? 'Market overview' : title.title}</h1><p className="page-description">{title.subtitle}</p></div><button className="button refresh-button" onClick={() => setRefresh(value => value + 1)} disabled={refreshing} aria-label="Refresh dashboard"><Icon name="refresh" size={16}/>{refreshing ? 'Refreshing' : 'Refresh data'}</button></div>
        <div className={'connection-strip ' + (scopeError ? 'connection-error' : '')} data-testid="connection-status"><span className={'connection-dot ' + (apiRecent ? 'is-reachable' : '')}/><strong>{scopeError ? 'Data refresh interrupted' : health.loading && !health.data ? 'Connecting to your server' : apiRecent ? 'API responding' : 'No recent API response'}</strong><span className="connection-detail">{scopeError || (health.data ? 'API checked ' + when(health.data.timestamp_utc, timezone) + ' · Source observations are shown separately.' : 'Waiting for authenticated server data.')}</span><button className="text-button" onClick={() => navigate('system')}>View system <Icon name="chevron" size={14}/></button></div>
        {scopeError && rows.length > 0 && <p className="stale-notice" role="alert">Showing previously loaded records. Their prices, reviews and source states must not be treated as current.</p>}
        {health.data?.warning && <div className="source-notice" data-testid="source-notice"><Icon name="info" size={14}/><span>{health.data.warning}</span></div>}
        {marketView && <>
          <div className="market-toolbar"><div className="asset-switch" aria-label="Market"><button data-testid="asset-GOLD" className={asset === 'GOLD' ? 'active' : ''} aria-pressed={asset === 'GOLD'} onClick={() => chooseAsset('GOLD')}><span className="asset-icon gold-icon">Au</span><span>Gold<small>Listed token contract</small></span></button><button data-testid="asset-BTC" className={asset === 'BTC' ? 'active' : ''} aria-pressed={asset === 'BTC'} onClick={() => chooseAsset('BTC')}><span className="asset-icon bitcoin-icon">₿</span><span>Bitcoin<small>Delta Exchange India</small></span></button></div><div className="mode-indicators"><span><i className={health.data?.live_ingestion_enabled ? 'flag-on' : ''}/>{health.data ? 'Ingestion ' + (health.data.live_ingestion_enabled ? 'enabled' : 'off') : 'Ingestion unknown'}</span><span><i className={health.data?.ai_enabled ? 'flag-on' : ''}/>{health.data ? 'AI ' + (health.data.ai_enabled ? 'enabled' : 'off') : 'AI unknown'}</span></div></div>
          {asset === 'GOLD' && <p className="instrument-note">Gold refers to the returned Delta token contract. It is not spot XAU/USD.</p>}
          {view !== 'ai' && <HorizonCards engines={engineRows} entries={rows} asset={asset} selected={horizon} onSelect={setHorizon} timezone={timezone} now={now} loading={engines.loading && !engines.data}/>}
          {view === 'sweeps' && <div className="sweep-explainer"><span className="sweep-explainer-icon"><Icon name="sweep" size={23}/></span><div><strong>A breach. A closed-candle reclaim. Then the checks.</strong><p>This view shows recorded candidates with sweep triggers. A wick alone does not establish hidden stops, liquidation activity or a future reversal.</p></div><span className="sweep-count">{filtered.length}<small>in selection</small></span></div>}
          {view === 'ai' ? <><div className="selection-strip"><span>{selected ? selected.candidate.symbol + ' · ' + selected.candidate.horizon_minutes + 'm · ' + when(selected.candidate.observed_at_utc, timezone, true) : 'Select a recorded candidate to inspect its review.'}</span>{selected && <span data-testid="candidate-status"><Badge value={lifecycle(selected, now)}/></span>}</div><div className="ai-review-layout"><section className="panel review-picker"><h2>Recorded candidates</h2><p className="muted">Latest 50 across both assets</p>{filtered.length ? filtered.map(entry => <button key={entry.candidate.candidate_id} data-testid={'candidate-row-' + entry.candidate.candidate_id} className={'review-picker-item ' + (selected?.candidate.candidate_id === entry.candidate.candidate_id ? 'is-selected' : '')} onClick={() => setSelectedId(entry.candidate.candidate_id)}><span><strong>{label(entry.candidate.direction)} · {entry.candidate.horizon_minutes}m</strong><small>{when(entry.candidate.observed_at_utc, timezone, true)}</small></span><Icon name="chevron" size={16}/></button>) : <Empty title="No reviews to select" body="Recorded candidates will appear here." icon="spark"/>}</section><AIReviewPanel entry={selected} timezone={timezone} expanded/></div></> : <div className="analysis-grid" id="selected-evidence"><SetupPanel entry={selected} timezone={timezone} now={now} loading={candidates.loading && !candidates.data} onViewAI={() => navigate('ai')}/><AIReviewPanel entry={selected} timezone={timezone} onExpand={() => navigate('ai')}/></div>}
          <SnapshotPanel snapshot={snapshot} loading={snapshotRead.loading} error={snapshotError} candidate={selected} timezone={timezone}/>
          {view !== 'ai' && <CandidateJournal entries={filtered} selectedId={selected?.candidate.candidate_id ?? null} onSelect={chooseEntry} timezone={timezone} now={now} loading={candidates.loading && !candidates.data} error={candidates.error} sweepsOnly={view === 'sweeps'} query={query} setQuery={setQuery} horizon={horizon} clearHorizon={() => setHorizon(null)}/>}
        </>}
        {view === 'research' && <ResearchView timezone={timezone} refreshToken={refresh}/>}
        {view === 'system' && <SystemView health={health.data} timezone={timezone} now={now} loading={health.loading} error={health.error} onRefresh={() => setRefresh(value => value + 1)}/>}
        <footer className="workspace-footer"><span><Icon name="shield" size={13}/> Read-only research · No order execution</span><span>Times shown in {timezone === 'UTC' ? 'UTC' : 'Asia/Kolkata'} · {view === 'research' ? 'Evidence refreshes on request' : 'Status polls every 15s after each response'}</span></footer>
      </main>
    </div>
  </div>
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>)
