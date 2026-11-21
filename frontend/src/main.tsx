import React, { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'
import './phase4.css'

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
type ResearchSummary = {
  status: 'NOT_STARTED' | 'INSUFFICIENT_DATA' | 'EXPLORATORY'; experiment_count: number; report_count: number; opportunity_count: number;
  latest_experiment: {experiment_id: string; created_at_utc: string; data_mode: string} | null; warning: string;
  selected_experiment_id: string | null; data_mode: string; external_calls_performed: number | null; real_notifications_sent: number | null; orders_placed: number | null; counter_scope: string;
  paper: {status: 'NOT_STARTED' | 'EXPLORATORY'; decisions: number; outcomes: number; explicit_gaps: number; evidence_modes: Record<string, number>; warning: string}
}
type ResearchExperiment = { experiment_id: string; created_at_utc: string; dataset_id: string; dataset_hash: string; config_hash: string; data_mode: string }
type EngineResearch = { engine: string; state: string; evaluations: number; candidates: number }
type ResearchDetail = {
  experiment_id: string; config_hash: string; manifest: {dataset_id: string; data_mode: string; provenance: string; coverage: unknown[]};
  holdout_state: 'NO_HOLDOUT' | 'HOLDOUT_PROTECTED' | 'HOLDOUT_OPENED';
  counts: {candidates: number; opportunities: number; outcomes: number; decisions: number}; engine_matrix: EngineResearch[];
  reports: {name: string; report: {classification?: string; partition?: string}}[];
  action_counts: {scope: string; external_calls: number; real_notifications: number; orders: number} | null
}
type PaperTransition = {event_id: string; opportunity_id: string; arm: string; state: string; occurred_at_utc: string}

function formatTime(utc: string) { return new Date(utc).toLocaleString('en-IN', {timeZone:'Asia/Kolkata',hour12:true}) + ' IST' }
function number(value: number) {return value.toLocaleString('en-US', {maximumFractionDigits:2})}
function latestAttempt(entry: Entry | undefined, provider: Attempt['provider']) {
  return entry?.review?.attempts.filter(attempt => attempt.provider === provider).at(-1)
}

function App() {
  const [view, setView] = useState<'market' | 'research'>('market')
  const [asset, setAsset] = useState<Asset>('GOLD')
  const [engines, setEngines] = useState<Engine[]>([])
  const [entries, setEntries] = useState<Entry[]>([])
  const [health, setHealth] = useState<Health | null>(null)
  const [research, setResearch] = useState<ResearchSummary | null>(null)
  const [researchExperiments, setResearchExperiments] = useState<ResearchExperiment[]>([])
  const [researchSelected, setResearchSelected] = useState<string | null>(null)
  const [researchDetail, setResearchDetail] = useState<ResearchDetail | null>(null)
  const [paperTransitions, setPaperTransitions] = useState<PaperTransition[]>([])
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    const refresh = async () => {
      try {
        const responses = await Promise.all(['/api/health', '/api/engines', '/api/candidates', '/api/research/summary', '/api/research/experiments', '/api/research/paper/transitions?limit=20'].map(u => fetch(u, {cache: 'no-store'})))
        if (responses.some(r => !r.ok)) throw new Error('Backend returned an error; see API logs')
        const [h, e, c, r, experiments, transitions] = await Promise.all(responses.map(response=>response.json())) as [Health, Engine[], Entry[], ResearchSummary, ResearchExperiment[], PaperTransition[]]
        if (!alive) return
        setHealth(h); setEngines(e); setEntries(c); setResearch(r); setResearchExperiments(experiments); setPaperTransitions(transitions); setResearchSelected(current => current ?? r.selected_experiment_id); setError(null)
      } catch (err) {
        if (alive) setError(err instanceof Error ? err.message : 'Backend unavailable')
      }
    }
    void refresh()
    const timer = window.setInterval(() => void refresh(), 15000)
    return () => { alive = false; window.clearInterval(timer) }
  }, [])
  useEffect(() => {
    let alive = true
    if (!researchSelected) { setResearchDetail(null); return () => { alive = false } }
    void fetch(`/api/research/experiments/${encodeURIComponent(researchSelected)}`, {cache: 'no-store'})
      .then(response => { if (!response.ok) throw new Error('Selected research experiment is unavailable'); return response.json() as Promise<ResearchDetail> })
      .then(detail => { if (alive) { setResearchDetail(detail); setError(null) } })
      .catch(err => { if (alive) { setResearchDetail(null); setError(err instanceof Error ? err.message : 'Research detail unavailable') } })
    return () => { alive = false }
  }, [researchSelected])
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
      <button className={'nav nav-button '+(view==='market'?'active':'')} onClick={()=>setView('market')}>▤ &nbsp; Market Overview</button>
      <div className="nav disabled">⌁ &nbsp; Order Flow <small>PLANNED</small></div>
      <div className="nav disabled">◉ &nbsp; AI Consensus <small>IN OVERVIEW</small></div>
      <button className={'nav nav-button '+(view==='research'?'active':'')} onClick={()=>setView('research')}>◷ &nbsp; Research <small>PHASE 5</small></button>
      <div className="nav disabled">⚙ &nbsp; Settings <small>PLANNED</small></div>
      <div className="sidebar-bottom"><span className="status-dot"/> Research mode<br/><small>No order execution</small></div>
    </aside>
    <main className="main">
      <header><div><p className="eyebrow">MARKET INTELLIGENCE / OVERVIEW</p><h1>Gold & Bitcoin <span>Intelligence</span></h1><p className="muted">Six independent horizons · Two independent AI analysts · Auditable evidence</p></div><span className="pill muted-pill">● RESEARCH ONLY</span></header>
      {error && <div className="alert" role="alert">Backend connection issue: {error}. No signals should be treated as live until the server reconnects.</div>}
      {view === 'research' ? <section className="research-page">
        <div className="section-head"><div><p className="eyebrow">HISTORICAL EVALUATION / PROSPECTIVE PAPER</p><h2>Research evidence</h2></div><span className="pill muted-pill">HYPOTHETICAL · EXPLORATORY</span></div>
        {!research ? <div className="panel research-empty"><strong>Loading research state…</strong><p>No result is inferred while the evidence store is unavailable.</p></div> : <>
          <div className="cards research-cards">
            <article className="engine"><span className="small-tag">HISTORICAL EXPERIMENTS</span><h3>{research.status}</h3><div className="metric">{research.experiment_count}</div><p className="muted">Isolated manifests and replay runs</p></article>
            <article className="engine"><span className="small-tag">PAPER LEDGER</span><h3>{research.paper.status}</h3><div className="metric">{research.paper.decisions}</div><p className="muted">Frozen decisions · {research.paper.outcomes} outcomes · {Object.keys(research.paper.evidence_modes).join(', ') || 'no evidence mode'}</p></article>
            <article className="engine"><span className="small-tag">DATA CLASSIFICATION</span><h3>{research.data_mode}</h3><div className="metric">{research.report_count}</div><p className="muted">Generated reports · {research.paper.explicit_gaps} explicit gaps</p></article>
          </div>
          <div className="panel research-selector"><label htmlFor="research-experiment">Selected experiment</label><select id="research-experiment" value={researchSelected ?? ''} onChange={event=>setResearchSelected(event.target.value || null)}><option value="">No dataset selected</option>{researchExperiments.map(experiment=><option key={experiment.experiment_id} value={experiment.experiment_id}>{experiment.experiment_id} · {experiment.data_mode}</option>)}</select>{researchDetail ? <div className="research-meta"><span>Dataset <b>{researchDetail.manifest.dataset_id}</b></span><span>Config <b>{researchDetail.config_hash.slice(0,12)}</b></span><span>Partition <b>{researchDetail.holdout_state}</b></span><span>Opportunities <b>{researchDetail.counts.opportunities}</b></span><span>Outcomes <b>{researchDetail.counts.outcomes}</b></span></div> : <p className="muted">Select a versioned experiment to view measured records.</p>}</div>
          {researchDetail && <div className="research-grid"><div className="panel"><div className="section-head"><h2>Six-engine evidence</h2><small>{researchDetail.manifest.data_mode}</small></div><div className="research-table">{researchDetail.engine_matrix.map(row=><div key={row.engine}><strong>{row.engine}</strong><span>{row.state}</span><span>{row.candidates} candidates / {row.evaluations} evaluations</span></div>)}</div></div><div className="panel"><div className="section-head"><h2>Partitions & reports</h2><small>{researchDetail.reports.length} immutable versions</small></div><div className="research-table">{researchDetail.reports.length ? researchDetail.reports.map(row=><div key={row.name}><strong>{row.name}</strong><span>{row.report.partition ?? 'UNPARTITIONED'}</span><span>{row.report.classification ?? 'INSUFFICIENT_DATA'}</span></div>) : <p className="muted">No report has been generated for this experiment.</p>}</div></div></div>}
          <div className="panel"><div className="section-head"><h2>Paper transitions</h2><small>Bounded latest 20</small></div><div className="research-table">{paperTransitions.length ? paperTransitions.map(row=><div key={row.event_id}><strong>{row.arm}</strong><span>{row.state}</span><span>{formatTime(row.occurred_at_utc)}</span></div>) : <p className="muted">No paper transitions recorded.</p>}</div></div>
          <div className="panel research-notice"><strong>Evidence limitations</strong><p>{research.warning}</p><p>{research.paper.warning}</p><p>Counter scope: {research.counter_scope} · External calls: {research.external_calls_performed ?? 'not measured'} · Real notifications: {research.real_notifications_sent ?? 'not measured'} · Orders: {research.orders_placed ?? 'unsupported'}</p></div>
        </>}
      </section> : <>
      <div className="toolbar"><div className="tabs"><button className={asset==='GOLD'?'chosen':''} onClick={()=>{setAsset('GOLD');setSelected(null)}}>◎ Gold <span>XAUT / listed contract</span></button><button className={asset==='BTC'?'chosen':''} onClick={()=>{setAsset('BTC');setSelected(null)}}>₿ Bitcoin <span>BTCUSD</span></button></div><div className="status-right"><span className={health?.live_ingestion_enabled?'dot-green':'dot-gray'}/> {health?.live_ingestion_enabled?'INGESTION ENABLED':'INGESTION OFF'} <span className="separator">|</span> GPT + Claude: {health?.ai_enabled?'ENABLED':'OFF'}</div></div>
      <section className="section"><div className="section-head"><h2>Detection engines</h2><small>Data-dependent · Never simulated signals</small></div><div className="cards">{[30,60,240].map((horizon,i)=>{const e=uiEngines.find(x=>x.horizon_minutes===horizon);return <div className="engine" key={horizon}><div className="engine-top"><span className="engine-icon">{['↗','◷','▥'][i]}</span><span className="small-tag">{['FAST','HOURLY','SESSION'][i]}</span></div><div className="engine-time">{horizon===30?'15–30 minutes':horizon===60?'Next 1 hour':'Next 2–4 hours'}</div><h3>{e?.state??'WAITING_FOR_DATA'}</h3><p className="muted">{e?`${e.symbol} · ${e.resolution} bars`:'Connect API to initialize'}</p><div className="hairline"/><div className="engine-footer"><span>Direction</span><strong>—</strong><span>Validated targets</span><strong>—</strong></div></div>})}</div></section>
      <div className="lower"><section className="panel"><div className="section-head"><h2>Recent candidate history</h2><small>{filtered.length} recorded</small></div>{!filtered.length?<div className="empty"><div className="empty-icon">⌁</div><strong>No verified candidates recorded</strong><p>Enable Delta market data and wait for a qualifying closed-candle event. No prices or alerts are fabricated.</p></div>:<div className="events">{filtered.map(e=><button key={e.candidate.candidate_id} className={'event '+(active?.candidate.candidate_id===e.candidate.candidate_id?'on':'')} onClick={()=>setSelected(e.candidate.candidate_id)}><div><strong>{e.candidate.direction} · {e.candidate.horizon_minutes}m</strong><small>{formatTime(e.candidate.observed_at_utc)}</small></div><div><span className={'tag '+(e.current_lifecycle_state==='CANDIDATE'&&e.consensus?.status==='CONFIRMED'?'confirmed':'')}>{e.current_lifecycle_state??'UNKNOWN'}</span><strong>${number(e.candidate.entry)}</strong></div></button>)}</div>}</section>
      <section className="panel"><div className="section-head"><h2>Dual AI confirmation</h2><small>Revision {active?.candidate_revision_id?.slice(0,12)??'—'}</small></div><div className="ai-grid"><div><div className="provider">◈ GPT analyst</div><strong>{gpt?.status??(health?.ai_enabled?'NOT_READY':'DISABLED')}</strong><p>{gpt ? `${gpt.returned_model??gpt.requested_model} · ${formatTime(gpt.completed_at_utc)}` : 'No attempt recorded'}</p></div><div><div className="provider">✳ Claude analyst</div><strong>{claude?.status??(health?.ai_enabled?'NOT_READY':'DISABLED')}</strong><p>{claude ? `${claude.returned_model??claude.requested_model} · ${formatTime(claude.completed_at_utc)}` : 'No attempt recorded'}</p></div></div><div className="decision"><strong>Current lifecycle</strong><span className="tag">{active?.current_lifecycle_state??'WAIT'}</span></div>{active?.current_lifecycle_reason&&<p className="explain">{active.current_lifecycle_reason}{active.current_lifecycle_at_utc?` · ${formatTime(active.current_lifecycle_at_utc)}`:''}</p>}<div className="decision"><strong>Historical review</strong><span className={'tag '+(active?.current_lifecycle_state==='CANDIDATE'&&active?.consensus?.status==='CONFIRMED'?'confirmed':'')}>{active?.consensus?.status??active?.review?.status??'UNREVIEWED'}</span></div><p className="explain">{active?.consensus?.reason ?? 'Only validated same-revision agreement plus fresh deterministic checks may confirm a research candidate.'}</p>{active&&<div className="detail"><div>Entry <b>${number(active.candidate.entry)}</b></div><div>Invalidation <b>${number(active.candidate.invalidation)}</b></div><div>Targets <b>{active.candidate.targets.map(v=>'$'+number(v)).join(' / ')}</b></div><div>Observed <b>{formatTime(active.candidate.observed_at_utc)}</b></div><div>Review deadline <b>{active.review?formatTime(active.review.deadline_at_utc):'Not queued'}</b></div><div>Expires <b>{formatTime(active.candidate.expires_at_utc)}</b></div></div>}</section></div>
      </>}
      <footer><div><span className="status-dot"/> WORKER: {workerHealth ? `${workerHealth.state} · verified ${formatTime(workerHealth.last_success_at_utc??workerHealth.heartbeat_at_utc)}` : 'No heartbeat'} </div><small>API response: {health?formatTime(health.timestamp_utc):'Not connected'}</small></footer>
    </main>
  </div>
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>)
