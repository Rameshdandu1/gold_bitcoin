import { expect, Page, test } from '@playwright/test'

const now = '2026-11-24T12:00:00Z'
const flow = { trade_count: 500, buy_contracts: '320', sell_contracts: '180', unclassified_contracts: '0', cvd_contracts: '140', elapsed_seconds: '240', latest_event_time_utc: now }
const snapshot = { observed_at_utc: now, source_quality: 'FRESH', regime: 'EXPANDING', warnings: [], order_flow: { last_500: flow, last_5000: { ...flow, trade_count: 5000 } }, book: { available: true, imbalance: '0.28', absorption: 'BUY_ABSORPTION' }, volatility: { atr: '42', projected_move: '63' }, vwap: '60200' }
const source = { source: 'delta_websocket', state: 'CONNECTED', detail: 'Validated public market event received', heartbeat_at_utc: now, last_success_at_utc: now }
const markets = (['GOLD', 'BTC'] as const).map((asset, index) => ({ asset, symbol: asset === 'GOLD' ? 'XAUTUSD' : 'BTCUSD', symbol_verified: true, state: 'HEALTHY', checks: { worker_current: true, discovery_verified: true, websocket_connected: true, executed_trade_fresh: true, book_fresh: true, reconciliation_valid: true }, price: index ? '60250.5' : '3622.05', price_state: 'FRESH', price_event_time_utc: now, price_received_at_utc: now, book: { state: 'FRESH', reason: 'valid', best_bid: index ? '60250' : '3622.01', best_ask: index ? '60250.5' : '3622.06', event_time_utc: now, sequence: 1234 }, reconciliation: { ...source, source: `candle_reconciliation:${asset === 'GOLD' ? 'XAUTUSD' : 'BTCUSD'}`, state: 'VALID', detail: 'matched=60; missing_stream=0; missing_rest=0; mismatched=0' }, snapshot, snapshot_state: 'RECORDED' }))
const engines = markets.flatMap(market => [30, 60, 240].map((horizon, index) => ({ id: `${market.asset}_${index === 0 ? 'FAST' : index === 1 ? 'HOURLY' : 'SESSION'}`, asset: market.asset, symbol: market.symbol, resolution: index === 0 ? '1m' : index === 1 ? '5m' : '15m', horizon_minutes: horizon, state: 'WATCH', detail: 'No confirmed trigger', updated_at_utc: now, evaluation_fresh: true, latest_record: null })))
const overview = { timestamp_utc: now, live_ingestion_enabled: true, ai_enabled: false, alerts_enabled: false, paper_collection_enabled: false, integrations: { openai_configured: true, anthropic_configured: true, coinglass_enabled: false, coinglass_configured: false, slack_configured: false }, markets, engines, sources: [source], budget: { day_utc: '2026-11-24', reserved_calls: 2, reserved_cost_microusd: 2100, admission_cost_microusd: 1500, reported_actual_cost_microusd: 430, usage_unknown_count: 1 }, queue: { review_jobs: { COMPLETE: 1 }, stale_review_leases: 0, alert_items: {}, stale_alert_leases: 0 }, daily_ai_budget_microusd: 5_000_000 }
const candidate = { candidate: { candidate_id: 'fixture-candidate', asset: 'GOLD', symbol: 'XAUTUSD', engine: 'GOLD_FAST', horizon_minutes: 30, direction: 'BULLISH', entry: 3620, invalidation: 3600, targets: [3630, 3640], observed_at_utc: now, expires_at_utc: '2026-11-24T12:30:00Z', trigger: 'Fixture trigger', feature_evidence: ['ATR expansion', 'positive cumulative delta'] }, candidate_revision_id: 'revision-fixture', current_lifecycle_state: 'CANDIDATE', current_lifecycle_reason: 'Recorded fixture', consensus: { status: 'WAIT', reason: 'Claude response invalid', supported_target_indices: [] }, review: { status: 'COMPLETE', attempts: [{ provider: 'OPENAI', status: 'SUCCEEDED', requested_model: 'gpt-fixture', returned_model: 'gpt-fixture', started_at_utc: now, completed_at_utc: now, failure_code: null, latency_ms: 870, metadata: {}, assessment: { decision: 'CONFIRM', direction: 'BULLISH', reason: 'Evidence aligns', agrees_with_invalidation: true, supported_target_indices: [1], counter_evidence: [], data_warnings: [] } }, { provider: 'ANTHROPIC', status: 'INVALID_ASSESSMENT', requested_model: 'claude-fixture', returned_model: null, started_at_utc: now, completed_at_utc: now, failure_code: 'INVALID_ASSESSMENT', latency_ms: 1120, metadata: {}, assessment: null }] } }

function candles(available = true) {
  return { asset: 'GOLD', symbol: 'XAUTUSD', resolution: '5m', data_state: available ? 'AVAILABLE' : 'UNAVAILABLE', candles: available ? Array.from({ length: 30 }, (_, index) => ({ open_time: new Date(Date.parse(now) - (30 - index) * 300_000).toISOString(), open: 3600 + index, high: 3605 + index, low: 3597 + index, close: 3603 + index, volume_contracts: 10 + index, available_at_utc: now })) : [], daily: { state: available ? 'AVAILABLE' : 'UNAVAILABLE', session_date_utc: '2026-11-24', open: available ? 3590 : null, previous_close: available ? 3580 : null, high: available ? 3635 : null, low: available ? 3575 : null, latest_close: available ? 3632 : null, change: available ? 52 : null, change_percent: available ? 1.45 : null }, warning: available ? 'Observed Delta candles; unavailable fields are not inferred.' : 'No factual REST candle observation is available.' }
}

async function mockOperatorApi(page: Page, candleAvailable = true) {
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url())
    let body: unknown
    if (url.pathname === '/api/market/overview') body = overview
    else if (url.pathname === '/api/market/candles') body = { ...candles(candleAvailable), asset: url.searchParams.get('asset') ?? 'GOLD', resolution: url.searchParams.get('resolution') ?? '5m' }
    else if (url.pathname === '/api/candidates') body = [candidate]
    else if (url.pathname === '/api/operator/settings') body = { features: { live_ingestion_enabled: true, ai_enabled: false, alerts_enabled: false, paper_collection_enabled: false, trading_enabled: false }, models: { openai: 'gpt-fixture', anthropic: 'claude-fixture' }, providers: { openai_configured: true, anthropic_configured: true, coinglass_enabled: false, coinglass_configured: false }, notifications: { dashboard_only_supported: true, slack_configured: false, external_notifications_enabled: false }, limits: { daily_ai_budget_microusd: 5_000_000, daily_ai_call_limit: 2, provider_call_limit: 1, provider_deadline_seconds: 90 }, market_data: { book_max_age_seconds: 10, reconciliation_max_age_seconds: 180, persistence_queue_size: 8192, persistence_batch_size: 256 }, risk: { fee_bps: '10', slippage_bps: '5', maximum_entry_drift_bps: '10', maximum_spread_bps: '10', minimum_net_reward_risk: '1.5' } }
    else if (url.pathname === '/api/health') body = { service: 'marketintel-api', timestamp_utc: now, live_ingestion_enabled: true, ai_enabled: false, alerts_enabled: false, paper_collection_enabled: false, trading_enabled: false, services: [{ service: 'GOLD_FAST', updated_at: now, state: 'WATCH', detail: 'No confirmed trigger' }], source_health: [source], budget: overview.budget, queue: overview.queue, warning: 'Research service. No order execution.' }
    else return route.fulfill({ status: 404, json: { detail: 'fixture route unavailable' } })
    await route.fulfill({ status: 200, json: body })
  })
  await page.route('**/readyz', route => route.fulfill({ status: 503, json: { ready: false, checks: { database_migration: true, operator_authentication: true, ai_configuration: true, alert_configuration: true, worker_heartbeat: true, required_market_sources: false, review_queue_recoverable: true, budget_available: true }, live_ingestion_enabled: true, ai_enabled: false, alerts_enabled: false, queue: overview.queue, budget: overview.budget } }))
}

test('operator can inspect charts, flow, AI evidence, settings and health', async ({ page }) => {
  await mockOperatorApi(page)
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Gold price chart' })).toBeVisible()
  await expect(page.getByTestId('candlestick-chart')).toBeVisible()
  await expect(page.getByText('Daily open')).toBeVisible()
  await page.getByRole('button', { name: '1h' }).click()
  await expect(page.getByRole('img', { name: 'GOLD 1h candlestick chart' })).toBeVisible()

  await page.getByRole('button', { name: 'Order Flow' }).click()
  await expect(page.getByRole('heading', { name: 'Order Flow' })).toBeVisible()
  await expect(page.getByText('Cumulative delta').first()).toBeVisible()

  await page.getByRole('button', { name: 'AI Consensus' }).click()
  await expect(page.getByRole('heading', { name: 'AI Consensus' })).toBeVisible()
  await expect(page.getByText('INVALID_ASSESSMENT').first()).toBeVisible()
  await expect(page.getByText('870 ms')).toBeVisible()

  await page.getByRole('button', { name: 'Settings' }).click()
  await expect(page.getByText('Dashboard-only review does not require Slack.')).toBeVisible()
  await expect(page.getByText('gpt-fixture')).toBeVisible()

  await page.getByRole('button', { name: 'System Health' }).click()
  await expect(page.getByRole('heading', { name: 'System Health' })).toBeVisible()
  await expect(page.getByText('required market sources')).toBeVisible()
  await expect(page.getByText('DISABLED').last()).toBeVisible()
})

test('market overview renders an explicit candle unavailable state', async ({ page }) => {
  await mockOperatorApi(page, false)
  await page.goto('/')
  await expect(page.getByText('Candles unavailable')).toBeVisible()
  await expect(page.getByText('No factual REST candle observation is available.', { exact: true })).toBeVisible()
})
