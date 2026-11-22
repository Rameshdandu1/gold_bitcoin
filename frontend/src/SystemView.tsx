import type { Health, Timezone } from './types'
import { price, number, when, age, label } from './format'
import { Icon, type IconName } from './Icon'
import './system.css'

type Props = {
  health: Health | null
  timezone: Timezone
  now: number
  loading: boolean
  error: string | null
  onRefresh: () => void
}

function stateTone(state: string): string {
  if (['ERROR', 'UNAVAILABLE', 'FAILED', 'REJECTED'].includes(state)) return 'issue'
  if (['DEGRADED', 'PARTIAL', 'STALE', 'USAGE_UNKNOWN', 'RECEIPT_UNKNOWN'].includes(state)) return 'attention'
  return 'neutral'
}

function IntegrationCard({ title, icon, enabled, description, status }: {
  title: string
  icon: IconName
  enabled?: boolean
  description: string
  status?: string
}) {
  return <article className="system-integration">
    <div className="system-integration-top"><span className="system-icon"><Icon name={icon} /></span><span className={`system-badge ${enabled === true ? 'system-badge-configured' : 'system-badge-neutral'}`}>{status ?? (enabled === true ? 'Enabled in configuration' : enabled === false ? 'Disabled in configuration' : 'Configuration unavailable')}</span></div>
    <h3>{title}</h3><p>{description}</p>
  </article>
}

function QueuePanel({ title, description, counts, staleLeases }: {
  title: string
  description: string
  counts: Record<string, number> | undefined
  staleLeases: number | undefined
}) {
  const entries = Object.entries(counts ?? {}).sort(([left], [right]) => left.localeCompare(right))
  return <article className="system-panel system-queue">
    <div className="system-panel-heading"><div><h2>{title}</h2><p>{description}</p></div><Icon name="layers" size={19} /></div>
    {entries.length ? <dl className="system-queue-list">{entries.map(([state, count]) => <div key={state}><dt><span className={`system-state-dot system-dot-${stateTone(state)}`} />{label(state)}</dt><dd>{number(count, 0)}</dd></div>)}</dl> : <div className="system-small-empty">{counts ? 'No recorded items in this queue.' : 'Queue counts have not been received.'}</div>}
    <div className={`system-lease-count${staleLeases !== undefined && staleLeases > 0 ? ' system-lease-attention' : ''}`}><span>Expired claimed leases</span><strong>{number(staleLeases, 0)}</strong></div>
  </article>
}

export default function SystemView({ health, timezone, now, loading, error, onRefresh }: Props) {
  const budget = health?.budget
  const sources = health?.source_health ?? []
  const services = health?.services ?? []
  const costs = [
    { title: 'Reported actual cost', value: budget?.reported_actual_cost_microusd, note: 'Recorded provider usage' },
    { title: 'Reserved cost', value: budget?.reserved_cost_microusd, note: 'Recorded budget reservations' },
    { title: 'Admission cost', value: budget?.admission_cost_microusd, note: 'Cost used for request admission' },
  ]

  return <section className="system-view" aria-label="System status" aria-busy={loading}>
    <header className="system-heading">
      <div><p className="system-eyebrow">OPERATIONS WORKSPACE</p><h2>System status</h2><p className="system-subtitle">Configuration, source observations and the work moving through your application.</p></div>
      <button className="system-refresh" type="button" onClick={onRefresh} disabled={loading}><Icon name="refresh" size={17} />{loading ? 'Refreshing…' : 'Refresh status'}</button>
    </header>

    <div className="system-read-status" aria-live="polite">
      <span className="system-read-label"><Icon name="clock" size={16} />Last API response</span>
      <strong>{when(health?.timestamp_utc, timezone, true)}</strong>
      {health && <span>{age(health.timestamp_utc, now)}</span>}
      <span className="system-read-note">Source observations have their own timestamps below.</span>
    </div>

    {error && <div className="system-notice system-notice-error" role="alert"><Icon name="info" size={20} /><div><strong>{health ? 'Refresh failed · showing the previous response' : 'System status unavailable'}</strong><p>{error}</p>{health && <p>Configuration, counts and recorded states below may have changed since the last successful read.</p>}</div></div>}

    {!health ? <div className="system-empty" role="status"><span className="system-empty-icon"><Icon name="pulse" size={28} /></span><h2>{loading ? 'Reading system status…' : 'No system response yet'}</h2><p>{loading ? 'Loading the application’s recorded configuration and health evidence.' : 'Refresh to retrieve configuration, source records and queue counts from the API.'}</p></div> : <>
      <section className="system-section" aria-labelledby="system-configuration-title">
        <div className="system-section-heading"><div><h2 id="system-configuration-title">Integration configuration</h2><p>Enabled flags describe configuration. Observed source health is reported separately.</p></div><span className="system-badge system-badge-neutral"><Icon name="shield" size={13} />Read only</span></div>
        <div className="system-integrations">
          <IntegrationCard title="Delta market data" icon="pulse" enabled={health.live_ingestion_enabled} description="Public market ingestion for discovered Bitcoin and tokenized-gold contracts." />
          <IntegrationCard title="GPT + Claude review" icon="spark" enabled={health.ai_enabled} description="Independent reviews of the same candidate evidence. Attempt results appear in AI Review." />
          <IntegrationCard title="Slack alerts" icon="link" enabled={health.alerts_enabled} description="Candidate notifications are handled by the alert queue. This flag does not verify delivery." />
          <IntegrationCard title="Paper collection" icon="research" enabled={health.paper_collection_enabled} description="Collection of hypothetical paper observations. Research retains their evidence mode." />
          <IntegrationCard title="CoinGlass context" icon="layers" status="Configuration not exposed" description="The API does not report this integration’s configuration flag. Look for recorded CoinGlass source observations below." />
          <IntegrationCard title="Order execution" icon="shield" status={health.trading_enabled ? 'Unexpected trading flag' : 'Unsupported'} description="The application provides market intelligence and research. It has no order-execution interface." />
        </div>
      </section>

      <section className="system-panel" aria-labelledby="system-sources-title">
        <div className="system-panel-heading"><div><h2 id="system-sources-title">Observed source health</h2><p>Last recorded states and timestamps; a recorded state alone does not establish current freshness.</p></div><span className="system-count">{number(sources.length, 0)} sources</span></div>
        {sources.length ? <div className="system-table-scroll" role="region" aria-label="Source observations table, scroll horizontally for all columns" tabIndex={0}><table className="system-table system-source-table">
          <caption className="system-visually-hidden">Recorded source states, heartbeat and success timestamps, state changes and details</caption>
          <thead><tr><th scope="col">Source</th><th scope="col">Recorded state</th><th scope="col">Last heartbeat</th><th scope="col">Last success</th><th scope="col">Details</th></tr></thead>
          <tbody>{sources.map(source => <tr key={source.source}>
            <th scope="row"><span className="system-source-name">{source.source}</span></th>
            <td><span className={`system-badge system-badge-${stateTone(source.state)}`}>{label(source.state)}</span>{source.transition_at_utc && <span className="system-cell-note">Changed {when(source.transition_at_utc, timezone, true)}</span>}</td>
            <td><span className="system-time">{when(source.heartbeat_at_utc, timezone, true)}</span><span className="system-cell-note">{age(source.heartbeat_at_utc, now)}</span></td>
            <td><span className="system-time">{when(source.last_success_at_utc, timezone, true)}</span><span className="system-cell-note">{age(source.last_success_at_utc, now)}</span></td>
            <td className="system-detail-cell"><span>{source.detail || source.reason || 'No detail recorded'}</span>{source.last_error && <span className="system-last-error">Last error: {source.last_error}</span>}</td>
          </tr>)}</tbody>
        </table></div> : <div className="system-small-empty">No source observations have been recorded. Integration flags above do not establish a working connection.</div>}
      </section>

      <section className="system-panel system-budget" aria-labelledby="system-budget-title">
        <div className="system-panel-heading"><div><h2 id="system-budget-title">AI usage & budget ledger</h2><p>Recorded application costs in USD. Reservations and admission cost are separate accounting views.</p></div><span className="system-badge system-badge-neutral">{budget ? `${budget.day_utc} · UTC day` : 'No budget data'}</span></div>
        <div className="system-budget-grid">{costs.map(cost => <div className="system-budget-stat" key={cost.title}><span>{cost.title}</span><strong>{price(cost.value === undefined ? undefined : cost.value / 1_000_000)}</strong><small>{cost.note}</small></div>)}<div className="system-budget-stat"><span>Reserved calls</span><strong>{number(budget?.reserved_calls, 0)}</strong><small>Ledger reservations for this UTC day</small></div></div>
        <div className={`system-budget-foot${budget && budget.usage_unknown_count > 0 ? ' system-budget-uncertain' : ''}`}><span><Icon name="info" size={16} /><strong>{number(budget?.usage_unknown_count, 0)}</strong> unknown-usage entries</span><p>{!budget ? 'Budget evidence has not been received.' : budget.usage_unknown_count > 0 ? 'Reported actual cost is incomplete while provider usage remains unknown.' : 'Reported actual cost reflects recorded usage; it is not an account invoice.'}</p></div>
      </section>

      <section className="system-section" aria-labelledby="system-queues-title">
        <div className="system-section-heading"><div><h2 id="system-queues-title">Processing queues</h2><p>Recorded counts by status, including terminal states.</p></div></div>
        <div className="system-queues">
          <QueuePanel title="AI review jobs" description="Independent review and decision processing" counts={health.queue?.review_jobs} staleLeases={health.queue?.stale_review_leases} />
          <QueuePanel title="Alert outbox" description="Notification records by their stored status" counts={health.queue?.alert_items} staleLeases={health.queue?.stale_alert_leases} />
        </div>
      </section>

      <section className="system-panel" aria-labelledby="system-services-title">
        <div className="system-panel-heading"><div><h2 id="system-services-title">Service records</h2><p>Persisted worker and engine reports, with their last update time.</p></div><span className="system-count">{number(services.length, 0)} records</span></div>
        {services.length ? <div className="system-service-list">{services.map(service => <article className="system-service" key={service.service}>
          <div className="system-service-identity"><span className="system-service-icon"><Icon name="grid" size={17} /></span><div><h3>{service.service}</h3><span className={`system-badge system-badge-${stateTone(service.state)}`}>{label(service.state)}</span></div></div>
          <p>{service.detail || 'No detail recorded'}</p><div className="system-service-time"><span>{when(service.updated_at, timezone, true)}</span><small>{age(service.updated_at, now)}</small></div>
        </article>)}</div> : <div className="system-small-empty">No service reports have been recorded.</div>}
      </section>
      {health.warning && <p className="system-footnote"><Icon name="info" size={15} />{health.warning}</p>}
    </>}
  </section>
}
