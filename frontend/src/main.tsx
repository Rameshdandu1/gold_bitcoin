import React, { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'

type Asset = 'GOLD' | 'BTC'
type Engine = { id: string; asset: Asset; symbol: string; resolution: string; horizon_minutes: number; state: string }
type Candidate = {
  candidate_id: string; asset: Asset; symbol: string; direction: 'BULLISH' | 'BEARISH'; horizon_minutes: number;
  entry: number; invalidation: number; targets: number[]; observed_at_utc: string; expires_at_utc: string;
  trigger: string; feature_evidence: string[]
}
type Consensus = { status: 'CONFIRMED' | 'REJECTED' | 'WAIT'; reason: string; supported_target_indices: number[] } | null
type Attempt = {
  provider: 'OPENAI' | 'ANTHROPIC'; status: string; requested_model: string;
  returned_model: string | null; completed_at_utc: string; failure_code: string | null
}
type Review = {
  status: string; created_at_utc: string; deadline_at_utc: string; attempts: Attempt[]
} | null
type Entry = {
  candidate: Candidate; consensus: Consensus;
  candidate_revision_id: string; review: Review;
  current_lifecycle_state: 'CANDIDATE' | 'INVALIDATED' | 'EXPIRED' | null;
  current_lifecycle_reason: string | null; current_lifecycle_at_utc: string | null
}
type SourceHealth = { source: string; state: string; heartbeat_at_utc: string; last_success_at_utc: string | null }
type Health = { live_ingestion_enabled: boolean; ai_enabled: boolean; alerts_enabled: boolean; trading_enabled: boolean; timestamp_utc: string; services: {service:string;updated_at:string;state:string;detail:string}[]; source_health: SourceHealth[]; warning: string }

function formatTime(utc: string) { return new Date(utc).toLocaleString('en-IN', {timeZone:'Asia/Kolkata',hour12:true}) + ' IST' }
function number(value: number) {return value.toLocaleString('en-US', {maximumFractionDigits:2})}
function latestAttempt(entry: Entry | undefined, provider: Attempt['provider']) {
  return entry?.review?.attempts.filter(attempt => attempt.provider === provider).at(-1)
}

function App() {
  const [asset, setAsset] = useState<Asset>('GOLD')
  const [engines, setEngines] = useState<Engine[]>([])
  const [entries, setEntries] = useState<Entry[]>([])
  const [health, setHealth] = useState<Health | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    const refresh = async () => {
      try {
        const responses = await Promise.all(['/api/health', '/api/engines', '/api/candidates'].map(u => fetch(u, {cache: 'no-store'})))
        if (responses.some(r => !r.ok)) throw new Error('Backend returned an error; see API logs')
        const [h, e, c] = await Promise.all(responses.map(r=>r.json())) as [Health, Engine[], Entry[]]
        if (!alive) return
        setHealth(h); setEngines(e); setEntries(c); setError(null)
      } catch (err) {
        if (alive) setError(err instanceof Error ? err.message : 'Backend unavailable')
      }
    }
    void refresh()
    const timer = window.setInterval(() => void refresh(), 15000)
    return () => { alive = false; window.clearInterval(timer) }
  }, [])
  const filtered = entries.filter(e=>e.candidate.asset === asset)
  const active = filtered.find(e => e.candidate.candidate_id === selected) ?? filtered[0]
  const gpt = latestAttempt(active, 'OPENAI')
  const claude = latestAttempt(active, 'ANTHROPIC')
  const workerHealth = health?.source_health.find(source => source.source === 'worker')
  const uiEngines = engines.filter(e => e.asset===asset).sort((a,b)=>a.horizon_minutes-b.horizon_minutes)
  return <div className="shell">
    <aside className="sidebar">
      <div className="identity"><span className="logo">◈</span><div><strong>VECTOR INTELLIGENCE</strong><small>DUAL AI RESEARCH</small></div></div>
      <div className="nav-heading">WORKSPACE</div>
      <div className="nav active">▤ &nbsp; Market Overview</div>
      <div className="nav disabled">⌁ &nbsp; Order Flow <small>PLANNED</small></div>
      <div className="nav disabled">◉ &nbsp; AI Consensus <small>IN OVERVIEW</small></div>
      <div className="nav disabled">◷ &nbsp; Backtesting <small>PLANNED</small></div>
      <div className="nav disabled">⚙ &nbsp; Settings <small>PLANNED</small></div>
      <div className="sidebar-bottom"><span className="status-dot"/> Research mode<br/><small>No order execution</small></div>
    </aside>
    <main className="main">
      <header><div><p className="eyebrow">MARKET INTELLIGENCE / OVERVIEW</p><h1>Gold & Bitcoin <span>Intelligence</span></h1><p className="muted">Six independent horizons · Two independent AI analysts · Auditable evidence</p></div><span className="pill muted-pill">● RESEARCH ONLY</span></header>
      {error && <div className="alert" role="alert">Backend connection issue: {error}. No signals should be treated as live until the server reconnects.</div>}
      <div className="toolbar"><div className="tabs"><button className={asset==='GOLD'?'chosen':''} onClick={()=>{setAsset('GOLD');setSelected(null)}}>◎ Gold <span>XAUT / listed contract</span></button><button className={asset==='BTC'?'chosen':''} onClick={()=>{setAsset('BTC');setSelected(null)}}>₿ Bitcoin <span>BTCUSD</span></button></div><div className="status-right"><span className={health?.live_ingestion_enabled?'dot-green':'dot-gray'}/> {health?.live_ingestion_enabled?'INGESTION ENABLED':'INGESTION OFF'} <span className="separator">|</span> GPT + Claude: {health?.ai_enabled?'ENABLED':'OFF'}</div></div>
      <section className="section"><div className="section-head"><h2>Detection engines</h2><small>Data-dependent · Never simulated signals</small></div><div className="cards">{[30,60,240].map((horizon,i)=>{const e=uiEngines.find(x=>x.horizon_minutes===horizon);return <div className="engine" key={horizon}><div className="engine-top"><span className="engine-icon">{['↗','◷','▥'][i]}</span><span className="small-tag">{['FAST','HOURLY','SESSION'][i]}</span></div><div className="engine-time">{horizon===30?'15–30 minutes':horizon===60?'Next 1 hour':'Next 2–4 hours'}</div><h3>{e?.state??'WAITING_FOR_DATA'}</h3><p className="muted">{e?`${e.symbol} · ${e.resolution} bars`:'Connect API to initialize'}</p><div className="hairline"/><div className="engine-footer"><span>Direction</span><strong>—</strong><span>Validated targets</span><strong>—</strong></div></div>})}</div></section>
      <div className="lower"><section className="panel"><div className="section-head"><h2>Recent candidate history</h2><small>{filtered.length} recorded</small></div>{!filtered.length?<div className="empty"><div className="empty-icon">⌁</div><strong>No verified candidates recorded</strong><p>Enable Delta market data and wait for a qualifying closed-candle event. No prices or alerts are fabricated.</p></div>:<div className="events">{filtered.map(e=><button key={e.candidate.candidate_id} className={'event '+(active?.candidate.candidate_id===e.candidate.candidate_id?'on':'')} onClick={()=>setSelected(e.candidate.candidate_id)}><div><strong>{e.candidate.direction} · {e.candidate.horizon_minutes}m</strong><small>{formatTime(e.candidate.observed_at_utc)}</small></div><div><span className={'tag '+(e.current_lifecycle_state==='CANDIDATE'&&e.consensus?.status==='CONFIRMED'?'confirmed':'')}>{e.current_lifecycle_state??'UNKNOWN'}</span><strong>${number(e.candidate.entry)}</strong></div></button>)}</div>}</section>
      <section className="panel"><div className="section-head"><h2>Dual AI confirmation</h2><small>Revision {active?.candidate_revision_id?.slice(0,12)??'—'}</small></div><div className="ai-grid"><div><div className="provider">◈ GPT analyst</div><strong>{gpt?.status??(health?.ai_enabled?'NOT_READY':'DISABLED')}</strong><p>{gpt ? `${gpt.returned_model??gpt.requested_model} · ${formatTime(gpt.completed_at_utc)}` : 'No attempt recorded'}</p></div><div><div className="provider">✳ Claude analyst</div><strong>{claude?.status??(health?.ai_enabled?'NOT_READY':'DISABLED')}</strong><p>{claude ? `${claude.returned_model??claude.requested_model} · ${formatTime(claude.completed_at_utc)}` : 'No attempt recorded'}</p></div></div><div className="decision"><strong>Current lifecycle</strong><span className="tag">{active?.current_lifecycle_state??'WAIT'}</span></div>{active?.current_lifecycle_reason&&<p className="explain">{active.current_lifecycle_reason}{active.current_lifecycle_at_utc?` · ${formatTime(active.current_lifecycle_at_utc)}`:''}</p>}<div className="decision"><strong>Historical review</strong><span className={'tag '+(active?.current_lifecycle_state==='CANDIDATE'&&active?.consensus?.status==='CONFIRMED'?'confirmed':'')}>{active?.consensus?.status??active?.review?.status??'UNREVIEWED'}</span></div><p className="explain">{active?.consensus?.reason ?? 'Only validated same-revision agreement plus fresh deterministic checks may confirm a research candidate.'}</p>{active&&<div className="detail"><div>Entry <b>${number(active.candidate.entry)}</b></div><div>Invalidation <b>${number(active.candidate.invalidation)}</b></div><div>Targets <b>{active.candidate.targets.map(v=>'$'+number(v)).join(' / ')}</b></div><div>Observed <b>{formatTime(active.candidate.observed_at_utc)}</b></div><div>Review deadline <b>{active.review?formatTime(active.review.deadline_at_utc):'Not queued'}</b></div><div>Expires <b>{formatTime(active.candidate.expires_at_utc)}</b></div></div>}</section></div>
      <footer><div><span className="status-dot"/> WORKER: {workerHealth ? `${workerHealth.state} · verified ${formatTime(workerHealth.last_success_at_utc??workerHealth.heartbeat_at_utc)}` : 'No heartbeat'} </div><small>API response: {health?formatTime(health.timestamp_utc):'Not connected'}</small></footer>
    </main>
  </div>
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>)
