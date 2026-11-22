export type Asset = 'GOLD' | 'BTC'
export type Timezone = 'Asia/Kolkata' | 'UTC'
export type View = 'overview' | 'sweeps' | 'ai' | 'research' | 'system'
export type Numeric = string | number | null

export interface Engine {
  id: string
  asset: Asset
  symbol: string
  resolution: string
  horizon_minutes: number
  state: string
  updated_at_utc?: string
  detail?: string
}

export interface Candidate {
  candidate_id: string
  snapshot_id: string
  asset: Asset
  symbol: string
  venue: string
  engine: string
  horizon_minutes: number
  candle_close_utc: string
  observed_at_utc: string
  expires_at_utc: string
  direction: 'BULLISH' | 'BEARISH'
  trigger: string
  entry: number
  invalidation: number
  targets: number[]
  feature_evidence: string[]
  counter_evidence: string[]
  source_quality: string
  rule_version: string
}

export interface Assessment {
  candidate_id: string
  candidate_revision_id: string
  snapshot_id: string
  analysis_input_hash: string
  asset: Asset
  symbol: string
  engine: string
  horizon_minutes: number
  direction: string
  decision: 'CONFIRM' | 'REJECT' | 'WAIT'
  supported_target_indices: number[]
  reason: string
  counter_evidence: string[]
  data_warnings: string[]
}

export interface ProviderAttempt {
  attempt_id: string
  provider: 'OPENAI' | 'ANTHROPIC'
  attempt_number: number
  status: string
  requested_model: string
  returned_model: string | null
  started_at_utc: string
  completed_at_utc: string
  input_tokens: number | null
  output_tokens: number | null
  failure_code: string | null
  assessment: Assessment | null
}

export interface CandidateEntry {
  candidate: Candidate
  candidate_revision_id: string
  consensus: {
    status: string
    reason: string
    decided_at_utc?: string
    evaluated_at_utc?: string
    supported_target_indices?: number[]
  } | null
  current_lifecycle_state: string | null
  current_lifecycle_reason: string | null
  current_lifecycle_at_utc: string | null
  review: {
    run_id: string
    status: string
    created_at_utc: string
    deadline_at_utc: string
    envelope_digest: string
    attempts: ProviderAttempt[]
  } | null
}

export interface SourceHealth {
  source: string
  state: string
  heartbeat_at_utc: string
  last_success_at_utc: string | null
  transition_at_utc?: string
  last_error?: string | null
  reason?: string
  detail?: string
}

export interface Budget {
  day_utc: string
  reserved_calls: number
  reserved_cost_microusd: number
  reported_actual_cost_microusd: number
  usage_unknown_count: number
  admission_cost_microusd: number
}

export interface Health {
  service: string
  timestamp_utc: string
  live_ingestion_enabled: boolean
  ai_enabled: boolean
  alerts_enabled: boolean
  paper_collection_enabled: boolean
  trading_enabled: boolean
  services: { service: string; updated_at: string; state: string; detail: string }[]
  source_health: SourceHealth[]
  budget?: Budget
  queue?: {
    review_jobs: Record<string, number>
    stale_review_leases: number
    alert_items: Record<string, number>
    stale_alert_leases: number
  }
  warning: string
}

export interface FlowWindow {
  trade_count: number
  classified_trade_count: number
  buy_contracts: Numeric
  sell_contracts: Numeric
  cvd_contracts: Numeric
  cvd_quote_notional: Numeric
}

export interface Snapshot {
  snapshot_id: string
  asset: Asset
  symbol: string
  venue: string
  engine: string
  observed_at_utc: string
  candle_close_utc: string
  source_quality: string
  regime: string
  vwap: Numeric
  warnings: string[]
  volatility: { atr: Numeric; projected_move: Numeric; relative_volume: Numeric; range_expansion: Numeric }
  book: {
    available: boolean
    observed_at_utc: string | null
    best_bid: Numeric
    best_ask: Numeric
    spread: Numeric
    imbalance: Numeric
    absorption: string
    reason: string
  }
  order_flow: { last_500: FlowWindow; last_5000: FlowWindow }
  liquidity_levels: { kind: string; price: Numeric; observed_at_utc: string; source: string; touches: number }[]
  structures: { kind: string; direction: string; resolution: string; level: Numeric; confirmed_at_utc: string; explanation: string }[]
  external_metrics: { provider: string; metric: string; symbol: string; value: Numeric; unit: string; observed_at_utc: string; received_at_utc: string | null; source_scope: string; entitlement: string }[]
}
