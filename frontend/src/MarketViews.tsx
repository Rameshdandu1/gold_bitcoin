import { useId, useState } from 'react'
import { Icon, type IconName } from './Icon'
import { age, assessmentMatches, isSweep, label, lifecycle, number, price, valueOf, when } from './format'
import type { Asset, CandidateEntry, Engine, ProviderAttempt, Snapshot, Timezone } from './types'

export function Badge({ value, children }: { value: string; children?: React.ReactNode }) {
  const positive = ['CONFIRMED', 'CONFIRM', 'SUCCEEDED', 'AVAILABLE', 'VALID', 'FRESH', 'BULLISH'].includes(value)
  const negative = ['REJECTED', 'REJECT', 'INVALIDATED', 'INVALID', 'ERROR', 'FAILED', 'BEARISH'].includes(value)
  const caution = ['WAIT', 'WATCH', 'STALE', 'INCOMPLETE', 'PARTIAL', 'UNAVAILABLE'].includes(value)
  return <span className={'badge ' + (positive ? 'badge-positive' : negative ? 'badge-negative' : caution ? 'badge-caution' : 'badge-neutral')}><span className="badge-dot"/>{children ?? label(value)}</span>
}

export function Empty({ title, body, icon = 'layers' }: { title: string; body: string; icon?: IconName }) {
  return <div className="empty-state"><div className="empty-icon"><Icon name={icon} size={28}/></div><h3>{title}</h3><p>{body}</p></div>
}

export function SectionHeading({ title, subtitle, children }: { title: string; subtitle?: string; children?: React.ReactNode }) {
  return <div className="section-heading"><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>{children}</div>
}

export function HorizonCards({ engines, entries, asset, selected, onSelect, timezone, now, loading }: {
  engines: Engine[]; entries: CandidateEntry[]; asset: Asset; selected: number | null
  onSelect: (horizon: number | null) => void; timezone: Timezone; now: number; loading: boolean
}) {
  const horizons = [
    { minutes: 30, title: 'Fast', detail: 'Sweep & reclaim', display: '30 min', icon: 'sweep' as const },
    { minutes: 60, title: 'Hourly', detail: 'Breakout & retest', display: '1 hour', icon: 'clock' as const },
    { minutes: 240, title: 'Session', detail: 'Market structure', display: '4 hours', icon: 'layers' as const },
  ]
  return <div className="horizon-grid">{horizons.map(item => {
    const engine = engines.find(row => row.asset === asset && row.horizon_minutes === item.minutes)
    const entry = entries.find(row => row.candidate.asset === asset && row.candidate.horizon_minutes === item.minutes)
    const state = entry ? lifecycle(entry, now) : null
    return <button className={'horizon-card ' + (selected === item.minutes ? 'is-selected' : '')} key={item.minutes} data-testid={'horizon-' + item.minutes} aria-pressed={selected === item.minutes} onClick={() => onSelect(selected === item.minutes ? null : item.minutes)}>
      <div className="horizon-top"><span className="horizon-icon"><Icon name={item.icon}/></span><span>{item.title}</span><strong>{item.display}</strong></div>
      <div className="horizon-state" title={engine ? 'Last engine result: ' + when(engine.updated_at_utc, timezone, true) : undefined}><Badge value={engine?.state ?? 'UNKNOWN'}>{engine ? label(engine.state) : loading ? 'Loading' : 'No engine record'}</Badge><Icon name="chevron" size={15}/></div>
      <p className="horizon-description">{item.detail} <span>· {engine?.resolution ?? '—'} candles</span></p>
      <p className="engine-observed">Last engine result: {engine ? age(engine.updated_at_utc, now) : 'not recorded'}</p>
      <div className="horizon-bottom"><div><small>Last candidate</small><strong className={entry ? entry.candidate.direction.toLowerCase() : ''}>{entry ? label(entry.candidate.direction) : 'Not recorded'}{state && state !== 'CANDIDATE' && <em> · {label(state)}</em>}</strong></div><div><small>Observed</small><strong title={when(entry?.candidate.observed_at_utc, timezone, true)}>{entry ? age(entry.candidate.observed_at_utc, now) : '—'}</strong></div></div>
    </button>
  })}</div>
}

function PriceMap({ entry }: { entry: CandidateEntry }) {
  const id = useId()
  const candidate = entry.candidate
  const points = [
    { name: 'Invalidation', short: 'INV', value: candidate.invalidation, kind: 'stop' },
    { name: 'Candidate entry', short: 'ENTRY', value: candidate.entry, kind: 'entry' },
    ...candidate.targets.map((value, index) => ({ name: 'Target ' + (index + 1), short: 'T' + (index + 1), value, kind: 'target' })),
  ].filter(row => Number.isFinite(row.value) && row.value > 0).sort((a, b) => b.value - a.value)
  if (points.length < 2) return <Empty title="Price levels unavailable" body="This record does not contain valid candidate geometry."/>
  const high = Math.max(...points.map(row => row.value))
  const low = Math.min(...points.map(row => row.value))
  const span = Math.max(high - low, high * 0.0001)
  const y = (value: number) => 24 + (high - value) / span * 194
  let previousLabel = -30
  const positioned = points.map(row => {
    const labelY = Math.max(y(row.value), previousLabel + 24)
    previousLabel = labelY
    return { ...row, labelY }
  })
  const height = Math.max(250, previousLabel + 28)
  const entryY = y(candidate.entry)
  const targetY = y(candidate.targets[candidate.targets.length - 1] ?? candidate.entry)
  return <><svg className="price-map" viewBox={'0 0 660 ' + height} role="img" aria-labelledby={id} data-testid="price-map">
    <title id={id}>Recorded candidate levels: {points.map(row => row.name + ' ' + price(row.value)).join(', ')}. Not a live price chart.</title>
    <defs><linearGradient id={id + '-fill'} x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stopColor="#0b8d82" stopOpacity=".11"/><stop offset="100%" stopColor="#0b8d82" stopOpacity=".015"/></linearGradient></defs>
    <rect x="26" y={Math.min(entryY, targetY)} width="460" height={Math.max(Math.abs(entryY - targetY), 1)} rx="6" fill={'url(#' + id + '-fill)'}/>
    {[26, 118, 210, 302, 394, 486].map(x => <line key={x} x1={x} x2={x} y1="12" y2={height - 15} stroke="#e7edef" strokeDasharray="3 5"/>)}
    {positioned.map(row => <g key={row.name} className={'map-level map-' + row.kind}>
      <line x1="26" x2="486" y1={y(row.value)} y2={y(row.value)} strokeWidth={row.kind === 'entry' ? 1.7 : 1} strokeDasharray={row.kind === 'entry' ? undefined : '5 5'}/>
      <circle cx={row.kind === 'entry' ? 252 : 68} cy={y(row.value)} r={row.kind === 'entry' ? 5 : 3}/>
      <path d={'M486 ' + y(row.value) + ' L508 ' + row.labelY + ' H518'} fill="none" strokeWidth="1"/>
      <rect x="520" y={row.labelY - 13} width="130" height="26" rx="5"/>
      <text x="529" y={row.labelY + 4} className="map-label">{row.short}</text>
      <text x="641" y={row.labelY + 4} textAnchor="end" className="map-price">{number(row.value, 2)}</text>
    </g>)}
    <text x="26" y={height - 1} className="map-caption">RECORDED LEVELS</text><text x="486" y={height - 1} textAnchor="end" className="map-caption">USD · NOT A PRICE PATH</text>
  </svg><dl className="level-summary">{points.filter(row => row.kind !== 'entry').map(row => <div key={row.name} className={'level-summary-' + row.kind}><dt>{row.name}</dt><dd>{price(row.value)}</dd></div>)}</dl></>
}

export function SetupPanel({ entry, timezone, now, loading, onViewAI }: {
  entry: CandidateEntry | null; timezone: Timezone; now: number; loading: boolean; onViewAI: () => void
}) {
  return <section className="panel setup-panel">
    <SectionHeading title="The setup" subtitle="Recorded geometry, with the evidence behind it."><span className="small-label"><Icon name="chart" size={14}/> Price-level map</span></SectionHeading>
    {!entry ? <Empty title={loading ? 'Loading candidate records' : 'Waiting for a qualifying setup'} body={loading ? 'Reading the latest recorded candidates from your server.' : 'A closed-candle event must pass the detector gates before a candidate appears. Prices will come from your data.'} icon="chart"/> : <>
      <div className="setup-summary"><div><span className="overline">Candidate entry · {entry.candidate.symbol}</span><div className="setup-price">{price(entry.candidate.entry)}<span className={'direction-mark ' + entry.candidate.direction.toLowerCase()}><Icon name="arrow" size={17}/>{label(entry.candidate.direction)}</span></div></div><div className="lifecycle-block"><span className="overline">Current lifecycle</span><div data-testid="candidate-status"><Badge value={lifecycle(entry, now)}/></div></div></div>
      <PriceMap entry={entry}/>
      <div className="setup-trigger"><span className="trigger-icon"><Icon name={isSweep(entry) ? 'sweep' : 'chart'} size={18}/></span><div><strong>{entry.candidate.trigger}</strong><p>{entry.candidate.engine} · {entry.candidate.horizon_minutes}m horizon · {entry.candidate.venue === 'delta_india' ? 'Delta Exchange India' : entry.candidate.venue}</p></div></div>
      <div className="setup-footer"><span><Icon name="clock" size={14}/> Observed {when(entry.candidate.observed_at_utc, timezone, true)}</span><button className="text-button" onClick={onViewAI}>Review evidence <Icon name="chevron" size={14}/></button></div>
      <details className="candidate-evidence"><summary>Detector evidence and counter-evidence</summary><div className="reason-list"><strong>Recorded support</strong>{entry.candidate.feature_evidence.length ? <ul>{entry.candidate.feature_evidence.map((reason, index) => <li key={index}>{reason}</li>)}</ul> : <p>No supporting items recorded.</p>}</div><div className="reason-list"><strong>Recorded counter-evidence</strong>{entry.candidate.counter_evidence.length ? <ul>{entry.candidate.counter_evidence.map((reason, index) => <li key={index}>{reason}</li>)}</ul> : <p>No counter-evidence items recorded; this does not establish their absence.</p>}</div></details>
      {lifecycle(entry, now) !== 'CANDIDATE' && <div className="inline-notice">Historical record. {entry.current_lifecycle_reason || 'The candidate is no longer within its active lifetime.'}</div>}
    </>}
  </section>
}

function latestAttempt(entry: CandidateEntry | null, provider: ProviderAttempt['provider']) {
  return entry?.review?.attempts.filter(row => row.provider === provider).sort((a, b) => b.attempt_number - a.attempt_number)[0]
}

function ProviderCard({ entry, provider, timezone, expanded }: { entry: CandidateEntry | null; provider: ProviderAttempt['provider']; timezone: Timezone; expanded: boolean }) {
  const result = latestAttempt(entry, provider)
  const assessment = result?.assessment
  const validIdentity = assessmentMatches(entry, assessment)
  const accepted = result?.status === 'SUCCEEDED' && validIdentity
  const verdict = accepted ? assessment?.decision : undefined
  const displayState = verdict ?? (result?.status === 'SUCCEEDED' ? 'UNAVAILABLE' : result?.status) ?? 'NOT_REVIEWED'
  const name = provider === 'OPENAI' ? 'GPT' : 'Claude'
  return <article className={'provider-card provider-' + name.toLowerCase()} data-testid={'provider-' + provider}>
    <div className="provider-heading"><span className="provider-avatar">{provider === 'OPENAI' ? <Icon name="spark" size={18}/> : <span>✳</span>}</span><div><h3>{name} analyst</h3><span>{result?.returned_model || result?.requested_model || 'No model response recorded'}</span></div><Badge value={displayState}>{result ? label(displayState) : 'Not reviewed'}</Badge></div>
    <p className="provider-reason">{result?.status === 'SUCCEEDED' && !validIdentity ? 'Assessment identity is missing or does not match this candidate and evidence packet. The verdict is withheld.' : accepted ? assessment?.reason : result?.failure_code ? label(result.failure_code) : 'Independent review will appear after an eligible candidate is processed.'}</p>
    {result && <div className="provider-foot"><span>Request: {label(result.status)}</span><span>{when(result.completed_at_utc, timezone)}</span></div>}
    {expanded && result && <div className="provider-expanded"><div className="detail-pairs"><div><span>Supported targets</span><strong>{accepted && assessment?.supported_target_indices?.length ? assessment.supported_target_indices.map(index => 'T' + index).join(', ') : 'None recorded'}</strong></div><div><span>Input / output tokens</span><strong>{number(result.input_tokens, 0)} / {number(result.output_tokens, 0)}</strong></div><div><span>Attempt</span><strong>{result.attempt_number}</strong></div><div><span>Requested model</span><strong>{result.requested_model || 'Not recorded'}</strong></div></div>
      {accepted && !!assessment?.counter_evidence?.length && <div className="reason-list"><strong>Counter-evidence</strong><ul>{assessment.counter_evidence.map((reason, index) => <li key={index}>{reason}</li>)}</ul></div>}
      {accepted && !!assessment?.data_warnings?.length && <div className="reason-list warning-list"><strong>Data warnings</strong><ul>{assessment.data_warnings.map((reason, index) => <li key={index}>{reason}</li>)}</ul></div>}
    </div>}
  </article>
}

export function AIReviewPanel({ entry, timezone, expanded = false, onExpand }: { entry: CandidateEntry | null; timezone: Timezone; expanded?: boolean; onExpand?: () => void }) {
  return <section className={'panel ai-panel ' + (expanded ? 'ai-expanded' : '')}>
    <SectionHeading title="Two independent perspectives" subtitle="GPT + Claude · one recorded evidence packet."><Icon name="spark" size={19}/></SectionHeading>
    <div className="provider-grid"><ProviderCard entry={entry} provider="OPENAI" timezone={timezone} expanded={expanded}/><ProviderCard entry={entry} provider="ANTHROPIC" timezone={timezone} expanded={expanded}/></div>
    <div className="consensus-box"><div><span className="overline">Historical review</span><Badge value={entry?.consensus?.status ?? 'UNREVIEWED'}/></div><p>{entry?.consensus?.reason || 'Agreement and fresh deterministic checks are required before a review can confirm.'}</p>{entry?.consensus && <small>Decided {when(entry.consensus.decided_at_utc ?? entry.consensus.evaluated_at_utc, timezone, true)} · Current lifecycle is shown separately.</small>}</div>
    {expanded && entry?.review && <div className="review-identity"><span>Evidence digest</span><code>{entry.review.envelope_digest}</code><span>Review deadline</span><strong>{when(entry.review.deadline_at_utc, timezone, true)}</strong></div>}
    {!expanded && onExpand && <button className="panel-link" onClick={onExpand}>Open full analyst review <Icon name="chevron" size={15}/></button>}
  </section>
}

export function SnapshotPanel({ snapshot, loading, error, candidate, timezone }: {
  snapshot: Snapshot | null; loading: boolean; error: string | null; candidate: CandidateEntry | null; timezone: Timezone
}) {
  const [tab, setTab] = useState<'flow' | 'levels' | 'context'>('flow')
  const flow = snapshot?.order_flow?.last_500
  const buy = valueOf(flow?.buy_contracts)
  const sell = valueOf(flow?.sell_contracts)
  const total = buy !== null && sell !== null ? buy + sell : null
  const buyPercent = total && buy !== null ? buy / total * 100 : null
  const book = snapshot?.book
  return <section className="panel evidence-panel" data-testid="snapshot-panel" data-snapshot-id={snapshot?.snapshot_id ?? ''}>
    <SectionHeading title="Market evidence" subtitle={snapshot ? 'Snapshot observed ' + when(snapshot.observed_at_utc, timezone, true) : 'Facts attached to the selected candidate.'}>
      <div className="segmented small-segments" aria-label="Evidence view">{(['flow', 'levels', 'context'] as const).map(value => <button key={value} onClick={() => setTab(value)} aria-pressed={tab === value}>{value === 'flow' ? 'Order flow' : value === 'levels' ? 'Liquidity levels' : 'Context'}</button>)}</div>
    </SectionHeading>
    {loading ? <Empty title="Loading recorded evidence" body="Fetching the snapshot for this candidate." icon="pulse"/> : error ? <div className="panel-error" role="alert"><Icon name="info"/><div><strong>Snapshot unavailable</strong><p>{error}</p></div></div> : !snapshot ? <Empty title={candidate ? 'Snapshot unavailable' : 'Choose a candidate to inspect'} body={candidate ? 'No snapshot was returned for this record. No market values have been inferred.' : 'Executed flow, reference levels and book observations appear with a recorded setup.'} icon="pulse"/> : <>
      <div className="snapshot-meta"><Badge value={snapshot.source_quality}>{label(snapshot.source_quality)} at observation</Badge><span>{snapshot.symbol} · {label(snapshot.regime)}</span><span className="recorded-label">Recorded snapshot, not a live quote</span></div>
      {tab === 'flow' && <><div className="evidence-metrics">
        <div><span>Relative volume</span><strong>{number(snapshot.volatility?.relative_volume)}{valueOf(snapshot.volatility?.relative_volume) !== null && <small>×</small>}</strong><p>At the trigger candle</p></div>
        <div><span>CVD · last 500</span><strong className={(valueOf(flow?.cvd_contracts) ?? 0) < 0 ? 'bearish' : ''}>{number(flow?.cvd_contracts)}<small> contracts</small></strong><p>{flow ? number(flow.trade_count, 0) + ' executed trades' : 'Not recorded'}</p></div>
        <div><span>Book imbalance</span><strong>{book?.available ? number(book.imbalance) : '—'}</strong><p>{book?.available ? 'Normalized −1 to +1' : book?.reason || 'Book unavailable'}</p></div>
        <div><span>Snapshot spread</span><strong>{book?.available ? price(book.spread) : '—'}</strong><p>{book?.available ? when(book.observed_at_utc, timezone) : 'No valid book observation'}</p></div>
      </div><div className="flow-section"><div className="flow-heading"><span>Classified aggressive flow <small>· last 500 trades</small></span><span>{flow ? number(flow.classified_trade_count, 0) + ' classified' : 'Not recorded'}</span></div>{buyPercent === null ? <p className="muted">Directional volume is unavailable.</p> : <><div className="flow-bar" role="img" aria-label={'Buy ' + number(buy) + ' contracts; sell ' + number(sell) + ' contracts'}><span style={{ width: buyPercent + '%' }}/></div><div className="flow-legend"><span><i className="legend-dot buy-dot"/>Buy <strong>{number(buy)} contracts</strong></span><span><i className="legend-dot sell-dot"/>Sell <strong>{number(sell)} contracts</strong></span></div></>}</div></>}
      {tab === 'levels' && <>{snapshot.liquidity_levels.length ? <div className="levels-list">{snapshot.liquidity_levels.slice(-8).reverse().map((level, index) => <div key={level.kind + level.observed_at_utc + index}><span className="level-icon"><Icon name="layers" size={15}/></span><div><strong>{label(level.kind)}</strong><small>{level.source} · {when(level.observed_at_utc, timezone)}</small></div><b>{price(level.price)}</b></div>)}</div> : <p className="inline-notice">No established technical levels were recorded for this snapshot.</p>}<p className="data-footnote">Technical reference levels from price structure. These are not liquidation clusters or proven resting orders.</p></>}
      {tab === 'context' && <><div className="context-grid"><div><span>ATR</span><strong>{price(snapshot.volatility?.atr)}</strong></div><div><span>Session VWAP proxy</span><strong>{price(snapshot.vwap)}</strong></div><div><span>Range expansion</span><strong>{number(snapshot.volatility?.range_expansion)}{valueOf(snapshot.volatility?.range_expansion) !== null && '×'}</strong></div><div><span>CVD · last 5,000</span><strong>{number(snapshot.order_flow?.last_5000?.cvd_contracts)} contracts</strong></div></div>
        {snapshot.external_metrics.length ? <div className="external-metrics">{snapshot.external_metrics.map((metric, index) => <div key={metric.metric + index}><span>{label(metric.metric)}<small>{metric.provider} · {metric.source_scope} · {when(metric.observed_at_utc, timezone)}</small></span><strong>{number(metric.value)} <small>{metric.unit}</small></strong></div>)}</div> : <p className="inline-notice">No external metrics were recorded. CoinGlass liquidation maps and Gold reference values are not inferred.</p>}
      </>}
      {!!snapshot.warnings.length && <details className="snapshot-warnings"><summary><Icon name="info" size={14}/>{snapshot.warnings.length} recorded data {snapshot.warnings.length === 1 ? 'warning' : 'warnings'}</summary><ul>{snapshot.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul></details>}
    </>}
  </section>
}

export function CandidateJournal({ entries, selectedId, onSelect, timezone, now, loading, error, sweepsOnly, query, setQuery, horizon, clearHorizon }: {
  entries: CandidateEntry[]; selectedId: string | null; onSelect: (entry: CandidateEntry) => void; timezone: Timezone; now: number
  loading: boolean; error: string | null; sweepsOnly: boolean; query: string; setQuery: (value: string) => void; horizon: number | null; clearHorizon: () => void
}) {
  const [expanded, setExpanded] = useState(false)
  const shown = expanded ? entries : entries.slice(0, 6)
  return <section className="panel journal-panel">
    <SectionHeading title={sweepsOnly ? 'Recorded sweep candidates' : 'Candidate journal'} subtitle="Filtered from the latest 50 candidate records across both assets.">
      <label className="search-field"><Icon name="search" size={17}/><input type="search" aria-label="Search candidates" placeholder="Search setups…" value={query} onChange={event => setQuery(event.target.value)}/></label>
    </SectionHeading>
    {horizon && <div className="active-filter"><span>{horizon}m horizon</span><button onClick={clearHorizon} aria-label="Clear horizon filter"><Icon name="close" size={13}/></button></div>}
    {error && <div className="inline-notice error-notice" role="alert">Candidate refresh failed. Any retained rows are historical. {error}</div>}
    {!entries.length ? <Empty title={loading ? 'Loading candidate history' : sweepsOnly ? 'No sweep candidates in this selection' : 'No candidates in this selection'} body={query || horizon ? 'Try another search or clear the horizon filter.' : 'Recorded candidates appear after a qualifying event. An empty history is not a market-direction signal.'} icon={sweepsOnly ? 'sweep' : 'layers'}/> : <>
      <div className="table-scroll"><table className="journal-table"><thead><tr><th scope="col">Observed</th><th scope="col">Setup / instrument</th><th scope="col">Direction</th><th scope="col">Horizon</th><th scope="col">Candidate entry</th><th scope="col">Lifecycle</th><th scope="col"><span className="sr-only">Open</span></th></tr></thead><tbody>{shown.map(entry => <tr key={entry.candidate.candidate_id} className={entry.candidate.candidate_id === selectedId ? 'selected-row' : ''}>
        <td><strong>{when(entry.candidate.observed_at_utc, timezone)}</strong><small>{age(entry.candidate.observed_at_utc, now)}</small></td>
        <td><button className="candidate-open" data-testid={'candidate-row-' + entry.candidate.candidate_id} onClick={() => onSelect(entry)}><strong>{isSweep(entry) ? 'Liquidity sweep' : /retest|breakout/i.test(entry.candidate.trigger) ? 'Breakout / retest' : 'Market structure'}</strong><small>{entry.candidate.symbol} · {entry.candidate.engine.replace(entry.candidate.asset + '_', '')}</small></button></td>
        <td><span className={'direction-text ' + entry.candidate.direction.toLowerCase()}><Icon name="arrow" size={13}/>{label(entry.candidate.direction)}</span></td>
        <td>{entry.candidate.horizon_minutes}m</td><td className="tabular">{price(entry.candidate.entry)}</td><td><Badge value={lifecycle(entry, now)}/></td><td><button className="row-action" onClick={() => onSelect(entry)} aria-label={'Open ' + entry.candidate.symbol + ' candidate observed ' + when(entry.candidate.observed_at_utc, timezone)}><Icon name="chevron" size={17}/></button></td>
      </tr>)}</tbody></table></div>
      <div className="journal-footer"><span>{entries.length} matching {entries.length === 1 ? 'record' : 'records'} · Selected records are historical evidence</span>{entries.length > 6 && <button className="text-button" onClick={() => setExpanded(!expanded)}>{expanded ? 'Show fewer' : 'Show all ' + entries.length}<Icon name="chevron" size={14}/></button>}</div>
    </>}
  </section>
}
