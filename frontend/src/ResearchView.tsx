import { useEffect, useState } from 'react'
import { getJson } from './api'
import './research.css'

type Timezone = 'Asia/Kolkata' | 'UTC'
type Summary = {
  status: string
  experiment_count: number
  report_count: number
  opportunity_count: number
  warning: string
}
type Experiment = { experiment_id: string; dataset_id: string; data_mode: string }
type Engine = { engine: string; evaluations: number; candidates: number }
type Report = {
  name: string
  created_at_utc: string
  report: { classification?: string; partition?: string }
}
type Detail = {
  experiment_id: string
  config_hash: string
  holdout_state: string
  manifest: { dataset_id: string; data_mode: string; provenance: string; content_hash: string }
  config: { evaluation_start_utc: string; evaluation_end_utc: string }
  counts: { opportunities: number; decisions: number; outcomes: number }
  engine_matrix: Engine[]
  reports: Report[]
  action_counts: { scope: string; external_calls: number; real_notifications: number; orders: number } | null
}
type Transition = {
  event_id: string
  opportunity_id: string
  revision_id: string
  arm: string
  state: string
  occurred_at_utc: string
}
type ReadState<T> = { path: string | null; data: T | null; loading: boolean; error: string | null }

/** Key each response to its request so a new selection never renders old evidence. */
function useRead<T>(path: string | null, refresh: string) {
  const [state, setState] = useState<ReadState<T>>({ path: null, data: null, loading: false, error: null })
  useEffect(() => {
    const controller = new AbortController()
    setState({ path, data: null, loading: Boolean(path), error: null })
    if (path) {
      void getJson<T>(path, controller.signal).then(
        data => {
          if (!controller.signal.aborted) setState({ path, data, loading: false, error: null })
        },
        error => {
          if (!controller.signal.aborted) setState({ path, data: null, loading: false, error: error instanceof Error ? error.message : 'Research evidence is unavailable.' })
        },
      )
    }
    return () => controller.abort()
  }, [path, refresh])
  return state.path === path ? state : { path, data: null, loading: Boolean(path), error: null }
}

const ENGINE_LABELS = [
  ['GOLD_FAST', 'Gold', '15–30 min'], ['GOLD_HOURLY', 'Gold', '1 hour'], ['GOLD_SESSION', 'Gold', '2–4 hours'],
  ['BTC_FAST', 'Bitcoin', '15–30 min'], ['BTC_HOURLY', 'Bitcoin', '1 hour'], ['BTC_SESSION', 'Bitcoin', '2–4 hours'],
] as const
const ARM_LABELS: Record<string, string> = {
  RULES_ONLY: 'Rules only', RULES_PLUS_GPT: 'Rules + GPT', RULES_PLUS_CLAUDE: 'Rules + Claude', RULES_PLUS_DUAL: 'Dual agreement',
}
const MODE_LABELS: Record<string, string> = {
  SYNTHETIC_FIXTURE: 'Synthetic fixture', DOWNLOADED_OHLC: 'Downloaded candles', RECORDED_AS_OBSERVED: 'Recorded market evidence',
  RECORDED_PROSPECTIVE_MODEL: 'Recorded model evidence', RETROSPECTIVE_LLM_EXPLORATORY: 'Retrospective AI · exploratory',
}
function label(value: string) { return value.replaceAll('_', ' ').toLowerCase() }
function count(value: number | undefined) { return typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString('en-IN') : '—' }
function time(value: string | undefined, timezone: Timezone) {
  if (!value || Number.isNaN(Date.parse(value))) return 'Not recorded'
  return new Intl.DateTimeFormat('en-IN', { timeZone: timezone, day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(new Date(value))
}
function EvidenceMark() {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M7 3h10l3 3v15H4V3h3Z" /><path d="M16 3v5h4M8 12h8M8 16h5" /></svg>
}
function StateMessage({ title, message, error = false }: { title: string; message: string; error?: boolean }) {
  return <div className={`research-state${error ? ' research-state-error' : ''}`} role={error ? 'alert' : 'status'}>
    <span className="research-state-icon"><EvidenceMark /></span><div><strong>{title}</strong><p>{message}</p></div>
  </div>
}

export default function ResearchView({ timezone, refreshToken = 0 }: { timezone: Timezone; refreshToken?: number }) {
  const [refresh, setRefresh] = useState(0)
  const [selected, setSelected] = useState('')
  const [page, setPage] = useState(0)
  const refreshKey = `${refreshToken}:${refresh}`
  const summary = useRead<Summary>('/api/research/summary', refreshKey)
  const experiments = useRead<Experiment[]>('/api/research/experiments?limit=50', refreshKey)
  const detail = useRead<Detail>(selected ? `/api/research/experiments/${encodeURIComponent(selected)}` : null, refreshKey)
  const transitions = useRead<Transition[]>(selected ? `/api/research/paper/transitions?experiment_id=${encodeURIComponent(selected)}&limit=20&offset=${page * 20}` : null, refreshKey)
  useEffect(() => {
    if (!selected && experiments.data?.length) setSelected(experiments.data[0].experiment_id)
  }, [experiments.data, selected])
  const data = detail.data?.experiment_id === selected ? detail.data : null
  const detailError = detail.error || (detail.data && !data ? 'The returned experiment does not match your selection. Its evidence has been withheld.' : null)
  const busy = summary.loading || experiments.loading || detail.loading || transitions.loading
  const protectedHoldout = data?.holdout_state === 'HOLDOUT_PROTECTED'
  const holdoutLabel = protectedHoldout ? 'Holdout protected' : data?.holdout_state === 'HOLDOUT_OPENED' ? 'Holdout opened' : data?.holdout_state === 'NO_HOLDOUT' ? 'No holdout configured' : 'Holdout status unavailable'

  return <section className="research-view" aria-label="Research evidence">
    <div className="research-heading">
      <div><p className="research-eyebrow">RESEARCH WORKSPACE</p><h2>Evidence before conviction.</h2><p className="research-subtitle">Inspect recorded experiments, independent model decisions and paper outcomes.</p>{summary.data && <div className="research-workspace-status"><span>Workspace status</span><span className="research-badge research-badge-neutral">{label(summary.data.status)}</span></div>}</div>
      <button className="research-refresh" type="button" onClick={() => setRefresh(value => value + 1)} disabled={busy}>
        <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d="M16 7a6.3 6.3 0 1 0 .4 5M16 3v4h-4" /></svg>{busy ? 'Refreshing…' : 'Refresh evidence'}
      </button>
    </div>

    {summary.error && <StateMessage error title="Workspace summary unavailable" message={summary.error} />}
    <div className="research-summary" aria-busy={summary.loading}>
      {[
        ['Recorded experiments', summary.data?.experiment_count, 'Versioned datasets and configurations'],
        ['Visible opportunity records', summary.data?.opportunity_count, 'Across experiments · holdout rules applied'],
        ['Saved reports', summary.data?.report_count, 'Existing research report versions'],
      ].map(([title, value, note]) => <article className="research-summary-card" key={String(title)}>
        <span className="research-small-label">{title}</span><strong className="research-summary-value">{count(typeof value === 'number' ? value : undefined)}</strong><span className="research-caption">{summary.loading ? 'Loading recorded totals…' : note}</span>
      </article>)}
    </div>

    <section className="research-panel research-dataset" aria-label="Dataset selection">
      <div className="research-panel-heading"><div><h2>Select an experiment</h2><p>Evidence stays tied to its original dataset and configuration.</p></div><span className="research-badge research-badge-neutral">Read only</span></div>
      {experiments.error ? <StateMessage error title="Experiment list unavailable" message={experiments.error} /> : <>
        <label className="research-select-label" htmlFor="research-experiment-select">Experiment <span>Most recent 50</span></label>
        <select id="research-experiment-select" className="research-select" value={selected} disabled={experiments.loading || !experiments.data?.length} onChange={event => { setSelected(event.target.value); setPage(0) }}>
          <option value="" disabled>{experiments.loading ? 'Loading experiments…' : 'Select a recorded experiment'}</option>
          {selected && !experiments.data?.some(item => item.experiment_id === selected) && <option value={selected}>{selected}</option>}
          {experiments.data?.map(item => <option key={item.experiment_id} value={item.experiment_id}>{item.experiment_id} · {MODE_LABELS[item.data_mode] ?? item.data_mode}</option>)}
        </select>
        {!experiments.loading && experiments.data?.length === 0 && <StateMessage title="No experiments recorded" message="Completed research runs will appear here with their source evidence and paper activity." />}
      </>}
      {detail.loading && <StateMessage title="Loading selected evidence" message="Retrieving the experiment and its visibility rules." />}
      {detailError && <StateMessage error title="Selected experiment unavailable" message={detailError} />}
      {data && <>
        <div className="research-dataset-tags"><span className={`research-badge ${data.manifest.data_mode === 'SYNTHETIC_FIXTURE' ? 'research-badge-amber' : 'research-badge-teal'}`}>{MODE_LABELS[data.manifest.data_mode] ?? data.manifest.data_mode}</span><span className={`research-badge ${protectedHoldout ? 'research-badge-amber' : 'research-badge-neutral'}`}>{holdoutLabel}</span><span className="research-caption">{data.manifest.dataset_id}</span></div>
        <div className="research-selected-counts">
          <div><span>Visible opportunities</span><strong>{count(data.counts.opportunities)}</strong></div>
          <div><span>Recorded arm decisions</span><strong>{count(data.counts.decisions)}</strong></div>
          <div><span>Recorded outcomes</span><strong>{count(data.counts.outcomes)}</strong></div>
          <div><span>Evidence classification</span><strong className="research-text-value">Hypothetical</strong></div>
        </div>
        {protectedHoldout && <p className="research-holdout-note">Protected and crossing holdout outcomes are withheld. This view does not open the holdout.</p>}
        <details className="research-provenance"><summary>Dataset provenance & evaluation window</summary><p>{data.manifest.provenance || 'Provenance was not provided.'}</p><dl>
          <div><dt>Evaluation window ({timezone === 'UTC' ? 'UTC' : 'IST'})</dt><dd>{time(data.config.evaluation_start_utc, timezone)} → {time(data.config.evaluation_end_utc, timezone)}</dd></div>
          <div><dt>Dataset identity</dt><dd className="research-monospace">{data.manifest.content_hash || 'Not recorded'}</dd></div>
          <div><dt>Configuration identity</dt><dd className="research-monospace">{data.config_hash}</dd></div>
        </dl></details>
      </>}
    </section>

    {data && <>
      <section className="research-panel" aria-label="Six engine evidence">
        <div className="research-panel-heading"><div><h2>Six engines. Separate evidence.</h2><p>Recorded evaluations and candidate events for this experiment.</p></div><span className="research-section-number">01 / COVERAGE</span></div>
        <div className="research-engine-grid">{ENGINE_LABELS.map(([engine, asset, horizon]) => {
          const observed = data.engine_matrix.find(row => row.engine === engine)
          return <article className="research-engine" key={engine}>
            <div className="research-engine-title"><span className={`research-asset-mark ${asset === 'Gold' ? 'research-asset-gold' : 'research-asset-btc'}`}>{asset === 'Gold' ? 'Au' : '₿'}</span><div><h3>{asset}</h3><span>{horizon}</span></div><span className={`research-observed-dot${observed ? ' research-observed-dot-recorded' : ''}`} title={observed ? 'Evaluations recorded' : 'No evaluations returned'} /></div>
            <dl><div><dt>Evaluations</dt><dd>{count(observed?.evaluations)}</dd></div><div><dt>Candidate events</dt><dd>{count(observed?.candidates)}</dd></div></dl>
            <p className="research-engine-footnote">{observed ? 'Recorded counts · no accuracy implied' : 'No engine evidence in this experiment'}</p>
          </article>
        })}</div>
        <p className="research-footnote">Engine counts describe evaluation history. Opportunity and outcome totals follow the experiment’s holdout visibility rules.</p>
      </section>

      <div className="research-bottom-grid">
        <section className="research-panel research-reports" aria-label="Saved research reports">
          <div className="research-panel-heading"><div><h2>Saved reports</h2><p>Existing analysis, preserved by version.</p></div><span className="research-count-badge">{count(data.reports.length)}</span></div>
          {data.reports.length ? <div className="research-report-list">{data.reports.map(report => <article className="research-report" key={report.name}>
            <span className="research-report-icon"><EvidenceMark /></span><div><h3>{report.name}</h3><p>{report.report.partition ? label(report.report.partition) : 'Partition not specified'} · {time(report.created_at_utc, timezone)}</p><span className="research-badge research-badge-neutral">{report.report.classification ? label(report.report.classification) : 'Classification unavailable'}</span></div>
          </article>)}</div> : <StateMessage title="No saved reports yet" message="A completed evaluation report will appear here. No performance result is inferred from the recorded counts." />}
        </section>
        <aside className="research-evidence-note">
          <span className="research-eyebrow">HOW TO READ THIS EVIDENCE</span><h2>Counts are evidence.<br />They are not a forecast.</h2><p>Synthetic and retrospective results do not establish live accuracy or profitability. Keep each asset, horizon and evidence mode separate.</p>
          <dl><div><dt>Calibrated probability</dt><dd>Unavailable</dd></div><div><dt>Live strategy performance</dt><dd>Not established by this view</dd></div></dl>
          <p className="research-evidence-source">{summary.data?.warning || 'Research outcomes are hypothetical. No empirical performance claim is made.'}</p>
        </aside>
      </div>

      <section className="research-panel" aria-label="Scoped paper transitions">
        <div className="research-panel-heading"><div><h2>Paper activity</h2><p>Selected experiment only · chronological pages of 20 · {timezone === 'UTC' ? 'UTC' : 'IST'}</p></div><span className="research-section-number">02 / AUDIT TRAIL</span></div>
        {transitions.loading ? <StateMessage title="Loading paper activity" message="Retrieving visible events for the selected experiment." /> : transitions.error ? <StateMessage error title="Paper activity unavailable" message={transitions.error} /> : transitions.data?.length ? <div className="research-table-scroll"><table className="research-activity-table"><thead><tr><th scope="col">Comparison arm</th><th scope="col">Recorded state</th><th scope="col">Opportunity</th><th scope="col">Occurred at</th></tr></thead><tbody>{transitions.data.map(event => <tr key={event.event_id}><td>{ARM_LABELS[event.arm] ?? event.arm}</td><td><span className="research-badge research-badge-neutral">{label(event.state)}</span></td><td><span className="research-monospace" title={`${event.opportunity_id} · revision ${event.revision_id}`}>{event.opportunity_id.slice(0, 12)}</span></td><td>{time(event.occurred_at_utc, timezone)}</td></tr>)}</tbody></table></div> : <StateMessage title={page ? 'No further visible events' : 'No visible paper activity'} message={protectedHoldout ? 'Protected outcomes remain hidden; no visible events were returned on this page.' : 'No paper events were returned on this page. Research outcomes and prospective paper observation are distinct.'} />}
        <div className="research-pagination"><span>{transitions.data?.length ? `Events ${page * 20 + 1}–${page * 20 + transitions.data.length}` : `Page ${page + 1}`}<span className="research-pagination-note"> · hypothetical paper evidence</span></span><div><button type="button" onClick={() => setPage(value => Math.max(0, value - 1))} disabled={page === 0 || transitions.loading}>Previous</button><button type="button" onClick={() => setPage(value => value + 1)} disabled={transitions.loading || transitions.data?.length !== 20}>Next</button></div></div>
      </section>
    </>}
  </section>
}
