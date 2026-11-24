import React, { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'
import './phase4.css'
import { OperatorMarket } from './OperatorMarket'
import { AIConsensusPage, OrderFlowPage, SettingsPage, SystemHealthPage } from './OperatorPages'

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

function App() {
  const [view, setView] = useState<'market' | 'order-flow' | 'ai-consensus' | 'research' | 'settings' | 'health'>('market')
  const [research, setResearch] = useState<ResearchSummary | null>(null)
  const [researchExperiments, setResearchExperiments] = useState<ResearchExperiment[]>([])
  const [researchSelected, setResearchSelected] = useState<string | null>(null)
  const [researchDetail, setResearchDetail] = useState<ResearchDetail | null>(null)
  const [paperTransitions, setPaperTransitions] = useState<PaperTransition[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (view !== 'research') return
    let alive = true
    const refresh = async () => {
      try {
        const responses = await Promise.all(['/api/research/summary', '/api/research/experiments', '/api/research/paper/transitions?limit=20'].map(u => fetch(u, {cache: 'no-store'})))
        if (responses.some(r => !r.ok)) throw new Error('Research backend returned an error; see API logs')
        const [r, experiments, transitions] = await Promise.all(responses.map(response=>response.json())) as [ResearchSummary, ResearchExperiment[], PaperTransition[]]
        if (!alive) return
        setResearch(r); setResearchExperiments(experiments); setPaperTransitions(transitions); setResearchSelected(current => current ?? r.selected_experiment_id); setError(null)
      } catch (err) {
        if (alive) setError(err instanceof Error ? err.message : 'Backend unavailable')
      }
    }
    void refresh()
    const timer = window.setInterval(() => void refresh(), 15000)
    return () => { alive = false; window.clearInterval(timer) }
  }, [view])
  useEffect(() => {
    let alive = true
    if (!researchSelected) { setResearchDetail(null); return () => { alive = false } }
    void fetch(`/api/research/experiments/${encodeURIComponent(researchSelected)}`, {cache: 'no-store'})
      .then(response => { if (!response.ok) throw new Error('Selected research experiment is unavailable'); return response.json() as Promise<ResearchDetail> })
      .then(detail => { if (alive) { setResearchDetail(detail); setError(null) } })
      .catch(err => { if (alive) { setResearchDetail(null); setError(err instanceof Error ? err.message : 'Research detail unavailable') } })
    return () => { alive = false }
  }, [researchSelected])
  return <div className="shell">
    <aside className="sidebar">
      <div className="identity"><span className="logo">◈</span><div><strong>VECTOR INTELLIGENCE</strong><small>DUAL AI RESEARCH</small></div></div>
      <div className="nav-heading">WORKSPACE</div>
      <button className={'nav nav-button '+(view==='market'?'active':'')} onClick={()=>setView('market')}>▤ &nbsp; Market Overview</button>
      <button className={'nav nav-button '+(view==='order-flow'?'active':'')} onClick={()=>setView('order-flow')}>⌁ &nbsp; Order Flow</button>
      <button className={'nav nav-button '+(view==='ai-consensus'?'active':'')} onClick={()=>setView('ai-consensus')}>◉ &nbsp; AI Consensus</button>
      <button className={'nav nav-button '+(view==='research'?'active':'')} onClick={()=>setView('research')}>◷ &nbsp; Research <small>PHASE 5</small></button>
      <button className={'nav nav-button '+(view==='settings'?'active':'')} onClick={()=>setView('settings')}>⚙ &nbsp; Settings</button>
      <button className={'nav nav-button '+(view==='health'?'active':'')} onClick={()=>setView('health')}>✚ &nbsp; System Health</button>
      <div className="sidebar-bottom"><span className="status-dot"/> Research mode<br/><small>No order execution</small></div>
    </aside>
    <main className="main">
      <header><div><p className="eyebrow">MARKET INTELLIGENCE / {view.replace('-', ' ').toUpperCase()}</p><h1>Gold & Bitcoin <span>Vector Intelligence</span></h1><p className="muted">Six independent horizons · Two independent AI analysts · Auditable evidence</p></div><span className="pill muted-pill">● RESEARCH ONLY</span></header>
      {view === 'research' && error && <div className="alert" role="alert">Backend connection issue: {error}. No signals should be treated as live until the server reconnects.</div>}
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
      </section> : view === 'market' ? <OperatorMarket/> : view === 'order-flow' ? <OrderFlowPage/> : view === 'ai-consensus' ? <AIConsensusPage/> : view === 'settings' ? <SettingsPage/> : <SystemHealthPage/>}
    </main>
  </div>
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>)
