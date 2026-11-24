import { useEffect, useState } from 'react'
import './operator-market.css'

type Asset = 'GOLD' | 'BTC'
type Horizon = 30 | 60 | 240
type Source = { source: string; state: string; detail: string; heartbeat_at_utc: string; last_success_at_utc: string | null }
type Flow = { trade_count: number; buy_contracts: string; sell_contracts: string; unclassified_contracts: string; cvd_contracts: string; elapsed_seconds: string; latest_event_time_utc: string | null }
type Snapshot = { observed_at_utc: string; source_quality: string; regime: string; warnings: string[]; order_flow: { last_500: Flow; last_5000: Flow }; book: { available: boolean; imbalance: string | null; absorption: string }; volatility: { atr: string; projected_move: string }; vwap: string | null }
type Market = { asset: Asset; symbol: string; symbol_verified: boolean; state: string; checks: Record<string, boolean>; price: string | null; price_state: string; price_event_time_utc: string | null; price_received_at_utc: string | null; book: { state: string; reason: string; best_bid: string | null; best_ask: string | null; event_time_utc: string | null; sequence: number | null }; reconciliation: Source | null; snapshot: Snapshot | null; snapshot_state: string }
type Attempt = { provider: 'OPENAI' | 'ANTHROPIC'; status: string; requested_model: string; returned_model: string | null; completed_at_utc: string | null; failure_code: string | null }
type Entry = { candidate: { candidate_id: string; asset: Asset; symbol: string; horizon_minutes: Horizon; direction: string; entry: number; invalidation: number; targets: number[]; observed_at_utc: string; expires_at_utc: string; trigger: string; feature_evidence: string[] }; candidate_revision_id: string; current_lifecycle_state: string | null; current_lifecycle_reason: string | null; consensus: { status: string; reason: string; supported_target_indices: number[] } | null; review: { status: string; attempts: Attempt[] } | null }
type Engine = { id: string; asset: Asset; symbol: string; resolution: string; horizon_minutes: Horizon; state: string; detail?: string; updated_at_utc?: string; evaluation_fresh: boolean; latest_record: Entry | null }
type Overview = { timestamp_utc: string; live_ingestion_enabled: boolean; ai_enabled: boolean; alerts_enabled: boolean; paper_collection_enabled: boolean; integrations: Record<string, boolean>; markets: Market[]; engines: Engine[]; sources: Source[]; budget: { day_utc: string; reserved_calls: number; admission_cost_microusd: number; reported_actual_cost_microusd: number; usage_unknown_count: number }; queue: { review_jobs: Record<string, number>; stale_review_leases: number }; daily_ai_budget_microusd: number }

const horizons: { value: Horizon; label: string }[] = [{ value: 30, label: '15–30 minutes' }, { value: 60, label: 'Next 1 hour' }, { value: 240, label: 'Next 2–4 hours' }]
const time = (v?: string | null) => v ? new Date(v).toLocaleString('en-IN', {timeZone: 'Asia/Kolkata', hour12: true}) + ' IST' : 'Not recorded'
const num = (v?: string | number | null) => v === null || v === undefined || !Number.isFinite(Number(v)) ? '—' : Number(v).toLocaleString('en-US', {maximumFractionDigits: 6})
const usd = (v?: string | number | null) => v === null || v === undefined ? '—' : '$' + num(v)
const label = (v: string) => v.replaceAll('_', ' ')

async function readJson<T>(url: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(url, { cache: 'no-store', signal })
  if (!response.ok) throw new Error(response.status === 401 ? 'Authentication required' : 'HTTP ' + response.status + ' for ' + url)
  return response.json() as Promise<T>
}

// One request at a time. On failure, discard the previous values rather than present stale data as current.
function usePolling<T>(url: string, interval = 15000) {
  const [result, setResult] = useState<{ url: string; data: T | null; error: string | null }>({url, data: null, error: null})
  useEffect(() => {
    const controller = new AbortController()
    let timer: number | undefined
    let alive = true
    setResult({url, data: null, error: null})
    const load = async () => {
      try {
        const data = await readJson<T>(url, controller.signal)
        if (alive) setResult({url, data, error: null})
      } catch (e) {
        if (alive) setResult({url, data: null, error: e instanceof Error ? e.message : 'Request failed'})
      } finally {
        if (alive) timer = window.setTimeout(() => void load(), interval)
      }
    }
    void load()
    return () => { alive = false; controller.abort(); window.clearTimeout(timer) }
  }, [url, interval])
  return result.url === url ? result : { url, data: null, error: null }
}

function FlowCard({ flow, count }: { flow: Flow; count: number }) {
  return <div className="op-flow"><strong>Last {count.toLocaleString()} executed trades</strong><small>{flow.trade_count.toLocaleString()} / {count.toLocaleString()} records · {flow.trade_count < count ? 'Incomplete count' : 'Count available'}</small><dl><dt>Aggressive buys (contracts)</dt><dd>{num(flow.buy_contracts)}</dd><dt>Aggressive sells (contracts)</dt><dd>{num(flow.sell_contracts)}</dd><dt>Unclassified (contracts)</dt><dd>{num(flow.unclassified_contracts)}</dd><dt>Delta (contracts)</dt><dd>{num(flow.cvd_contracts)}</dd><dt>Window duration (seconds)</dt><dd>{num(flow.elapsed_seconds)}</dd></dl><small>Last trade: {time(flow.latest_event_time_utc)}</small></div>
}

function Proposal({ entry }: { entry: Entry }) {
  const c = entry.candidate
  return <><dl><dt>Direction</dt><dd>{c.direction}</dd><dt>Proposed entry</dt><dd>{usd(c.entry)}</dd><dt>Invalidation</dt><dd>{usd(c.invalidation)}</dd><dt>Proposed targets</dt><dd>{c.targets.map(usd).join(' / ')}</dd><dt>Recorded lifecycle</dt><dd>{entry.current_lifecycle_state ?? 'UNKNOWN'}</dd><dt>Recorded review</dt><dd>{entry.consensus?.status ?? entry.review?.status ?? 'UNREVIEWED'}</dd><dt>Observed</dt><dd>{time(c.observed_at_utc)}</dd><dt>Expires</dt><dd>{time(c.expires_at_utc)}</dd></dl><p className="muted">{c.trigger}</p>{entry.current_lifecycle_reason && <p className="muted">{entry.current_lifecycle_reason}</p>}<p className="muted">Historical proposal and review; not current trade authorization.</p></>
}

export function OperatorMarket() {
  const [asset, setAsset] = useState<Asset>('GOLD')
  const [horizon, setHorizon] = useState<Horizon | 'ALL'>('ALL')
  const [page, setPage] = useState(0)
  const [selected, setSelected] = useState<string | null>(null)
  const overview = usePolling<Overview>('/api/market/overview')
  const history = usePolling<Entry[]>('/api/candidates?asset=' + asset + '&limit=10&offset=' + page * 10 + (horizon === 'ALL' ? '' : '&horizon_minutes=' + horizon))
  const data = overview.data
  const market = data?.markets.find(m => m.asset === asset)
  const entries = history.data ?? []
  const active = entries.find(e => e.candidate.candidate_id === selected) ?? entries[0]
  return <div className="operator-market">
    <div className="toolbar"><div className="tabs">{(['GOLD', 'BTC'] as const).map(a => <button key={a} className={asset === a ? 'chosen' : ''} onClick={() => { setAsset(a); setPage(0); setSelected(null); setHorizon('ALL') }}>{a === 'GOLD' ? 'Gold' : 'Bitcoin'}</button>)}</div><div className="muted">Read-only diagnostics · refresh every 15s</div></div>
    {overview.error && <div className="alert" role="alert">Market overview unavailable: {overview.error}. Previous values are not shown as current.</div>}
    {!data && !overview.error && <p className="muted" role="status">Loading market evidence…</p>}
    {data && <>
      <div className="op-price-grid">{data.markets.map(m => <article key={m.asset} className="panel op-price"><div className="op-title"><strong>{m.asset === 'GOLD' ? 'Gold token' : 'Bitcoin'} · {m.symbol}</strong><span className={'op-state ' + (m.state === 'HEALTHY' ? 'ok' : 'warn')}>{m.state}</span></div><div className="op-number">{usd(m.price)}</div><p className="muted">{m.price_state} · Last recorded executed trade, not mark or spot price</p><p className="muted">{time(m.price_event_time_utc)} · {m.symbol_verified ? 'Discovered instrument verified' : 'Symbol preference / unverified'}</p></article>)}</div>
      <p className="muted op-note">Ingestion {data.live_ingestion_enabled ? 'enabled' : 'off'} · Dual AI {data.ai_enabled ? 'enabled' : 'off'} · API response {time(data.timestamp_utc)}. Enabled is not the same as healthy.</p>
      <section className="section"><div className="section-head"><h2>Detection engines</h2><small>Latest evaluations and recorded proposals</small></div><div className="cards">{horizons.map(h => {const e = data.engines.find(row => row.asset === asset && row.horizon_minutes === h.value); return <article className="engine op-engine" key={h.value}><p className="muted">{h.label} · {e?.symbol ?? 'Unknown'} · {e?.resolution ?? '—'}</p><h3>{e?.evaluation_fresh ? e.state : 'STALE / NOT EVALUATED'}</h3><p className="op-reason">{e?.detail ?? 'No evaluation reason recorded'}</p><small className="muted">Last recorded state: {e?.state ?? '—'} · {time(e?.updated_at_utc)}</small><div className="hairline"/>{e?.latest_record ? <Proposal entry={e.latest_record}/> : <p className="muted">No recorded proposal for this horizon.</p>}</article>})}</div></section>
      {market && <section className="section op-two"><article className="panel op-panel"><h2>Market data health · {market.symbol}</h2><dl>{Object.entries(market.checks).map(([k,v]) => <div className="op-dl-row" key={k}><dt>{label(k)}</dt><dd className={v ? 'ok' : 'warn'}>{v ? 'PASS' : 'NOT READY'}</dd></div>)}</dl><h3>Reconciliation</h3><p className="op-reason">{market.reconciliation?.state ?? 'NOT RECORDED'} · {market.reconciliation?.detail ?? 'No reconciliation evidence'}</p><small className="muted">{time(market.reconciliation?.heartbeat_at_utc)}</small><h3>Order book</h3><p className="op-reason">{market.book.state} · {market.book.reason}</p><dl><dt>Bid / Ask</dt><dd>{usd(market.book.best_bid)} / {usd(market.book.best_ask)}</dd><dt>Sequence</dt><dd>{market.book.sequence ?? '—'}</dd><dt>Event time</dt><dd>{time(market.book.event_time_utc)}</dd></dl></article><article className="panel op-panel"><h2>Recorded FAST order-flow evidence</h2><p className="muted">{market.snapshot_state} · {time(market.snapshot?.observed_at_utc)} · not a live tick-by-tick view</p>{market.snapshot ? <><div className="op-flow-grid"><FlowCard flow={market.snapshot.order_flow.last_500} count={500}/><FlowCard flow={market.snapshot.order_flow.last_5000} count={5000}/></div><p className="muted">Snapshot quality: {market.snapshot.source_quality} · regime: {market.snapshot.regime} · book imbalance: {num(market.snapshot.book.imbalance)} · absorption proxy: {market.snapshot.book.absorption}</p><p className="muted">ATR: {num(market.snapshot.volatility.atr)} · projected range heuristic: {num(market.snapshot.volatility.projected_move)} · VWAP: {num(market.snapshot.vwap)}</p>{market.snapshot.warnings.map((w,i)=><p key={i} className="muted">{w}</p>)}</> : <p className="muted">No recorded FAST feature snapshot. No flow values inferred.</p>}</article></section>}
      <section className="section op-two"><article className="panel op-panel"><h2>Integrations and AI usage</h2><dl>{Object.entries(data.integrations).map(([k,v])=><div className="op-dl-row" key={k}><dt>{label(k)}</dt><dd>{v?'YES':'NO'}</dd></div>)}<dt>Dual review</dt><dd>{data.ai_enabled ? 'Enabled (not proof of connectivity)' : 'Disabled'}</dd><dt>UTC-day reserved calls</dt><dd>{data.budget.reserved_calls}</dd><dt>Reported actual spend</dt><dd>{usd(data.budget.reported_actual_cost_microusd / 1e6)}</dd><dt>Admission spend / cap</dt><dd>{usd(data.budget.admission_cost_microusd / 1e6)} / {usd(data.daily_ai_budget_microusd / 1e6)}</dd><dt>Unknown usage</dt><dd>{data.budget.usage_unknown_count}</dd><dt>Stale review leases</dt><dd>{data.queue.stale_review_leases}</dd></dl><small className="muted">Configuration only; no test requests are made by this dashboard. Budget day: {data.budget.day_utc} UTC.</small></article><article className="panel op-panel"><h2>Source heartbeat diagnostics</h2>{data.sources.length ? <div className="op-sources">{data.sources.map(s => <div key={s.source}><strong>{s.source} · {s.state}</strong><p className="muted">{s.detail}</p><small>{time(s.heartbeat_at_utc)}</small></div>)}</div> : <p className="muted">No source health records yet.</p>}</article></section>
    </>}
    <section className="section op-two"><article className="panel op-panel"><div className="op-title"><h2>Candidate history · {asset}</h2><label className="muted">Horizon <select value={horizon} onChange={event => {const value=event.target.value; setHorizon(value === 'ALL' ? 'ALL' : Number(value) as Horizon); setPage(0); setSelected(null)}}><option value="ALL">All</option>{horizons.map(h=><option key={h.value} value={h.value}>{h.label}</option>)}</select></label></div>{history.error ? <p role="alert" className="op-reason">{history.error}</p> : !history.data ? <p className="muted">Loading history…</p> : entries.length ? <div className="events">{entries.map(e=><button className={'event ' + (active?.candidate.candidate_id === e.candidate.candidate_id ? 'on' : '')} key={e.candidate.candidate_id} onClick={()=>setSelected(e.candidate.candidate_id)}><div><strong>{e.candidate.direction} · {e.candidate.horizon_minutes}m</strong><small>{e.candidate.symbol} · {time(e.candidate.observed_at_utc)}</small></div><div>{e.current_lifecycle_state ?? 'UNKNOWN'} · {usd(e.candidate.entry)}</div></button>)}</div> : <p className="muted">No candidates on this page for the selected asset and horizon.</p>}<div className="op-pagination"><button disabled={page===0} onClick={()=>{setPage(p=>p-1);setSelected(null)}}>Previous</button><span className="muted">Page {page+1}</span><button disabled={!history.data || entries.length < 10} onClick={()=>{setPage(p=>p+1);setSelected(null)}}>Next</button></div></article><article className="panel op-panel"><h2>Selected proposal & independent review</h2>{active ? <><Proposal entry={active}/>{(['OPENAI','ANTHROPIC'] as const).map(p=>{const attempt=active.review?.attempts.filter(a=>a.provider===p).at(-1);return <div className="op-review" key={p}><strong>{p === 'OPENAI' ? 'GPT' : 'Claude'} · {attempt?.status ?? 'NO RECORDED ATTEMPT'}</strong><p className="muted">{attempt ? (attempt.returned_model ?? attempt.requested_model) + ' · ' + time(attempt.completed_at_utc) : 'No provider response stored for this revision'}</p>{attempt?.failure_code && <p className="op-reason">{attempt.failure_code}</p>}</div>})}<p className="muted">{active.consensus?.reason ?? 'No recorded consensus'}</p><details><summary>Quantitative evidence</summary>{active.candidate.feature_evidence.map((e,i)=><p className="muted" key={i}>{e}</p>)}</details></> : <p className="muted">Select a recorded candidate to see its revision-specific reviews.</p>}</article></section>
  </div>
}
