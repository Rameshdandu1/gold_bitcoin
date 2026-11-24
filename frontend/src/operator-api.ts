import { useEffect, useState } from 'react'

export type Asset = 'GOLD' | 'BTC'
export type Horizon = 30 | 60 | 240
export type Source = { source: string; state: string; detail: string; heartbeat_at_utc: string; last_success_at_utc: string | null }
export type Flow = { trade_count: number; buy_contracts: string; sell_contracts: string; unclassified_contracts: string; cvd_contracts: string; elapsed_seconds: string; latest_event_time_utc: string | null }
export type Snapshot = { observed_at_utc: string; source_quality: string; regime: string; warnings: string[]; order_flow: { last_500: Flow; last_5000: Flow }; book: { available: boolean; imbalance: string | null; absorption: string }; volatility: { atr: string; projected_move: string }; vwap: string | null }
export type Market = { asset: Asset; symbol: string; symbol_verified: boolean; state: string; checks: Record<string, boolean>; price: string | null; price_state: string; price_event_time_utc: string | null; price_received_at_utc: string | null; book: { state: string; reason: string; best_bid: string | null; best_ask: string | null; event_time_utc: string | null; sequence: number | null }; reconciliation: Source | null; snapshot: Snapshot | null; snapshot_state: string }
export type Assessment = { decision: string; direction: string; reason: string; agrees_with_invalidation: boolean; supported_target_indices: number[]; counter_evidence: string[]; data_warnings: string[] }
export type Attempt = { provider: 'OPENAI' | 'ANTHROPIC'; status: string; requested_model: string; returned_model: string | null; started_at_utc: string; completed_at_utc: string | null; failure_code: string | null; latency_ms: number; assessment: Assessment | null; metadata: Record<string, string> }
export type Entry = { candidate: { candidate_id: string; asset: Asset; symbol: string; engine: string; horizon_minutes: Horizon; direction: string; entry: number; invalidation: number; targets: number[]; observed_at_utc: string; expires_at_utc: string; trigger: string; feature_evidence: string[]; counter_evidence?: string[] }; candidate_revision_id: string; current_lifecycle_state: string | null; current_lifecycle_reason: string | null; consensus: { status: string; reason: string; supported_target_indices: number[]; gates?: { code: string; passed: boolean; detail: string }[] } | null; review: { status: string; attempts: Attempt[] } | null }
export type Engine = { id: string; asset: Asset; symbol: string; resolution: string; horizon_minutes: Horizon; state: string; detail?: string; updated_at_utc?: string; evaluation_fresh: boolean; latest_record: Entry | null }
export type Overview = { timestamp_utc: string; live_ingestion_enabled: boolean; ai_enabled: boolean; alerts_enabled: boolean; paper_collection_enabled: boolean; integrations: Record<string, boolean>; markets: Market[]; engines: Engine[]; sources: Source[]; budget: { day_utc: string; reserved_calls: number; reserved_cost_microusd?: number; admission_cost_microusd: number; reported_actual_cost_microusd: number; usage_unknown_count: number }; queue: { review_jobs: Record<string, number>; stale_review_leases: number; alert_items?: Record<string, number>; stale_alert_leases?: number }; daily_ai_budget_microusd: number }
export type Candle = { open_time: string; open: number; high: number; low: number; close: number; volume_contracts: number; available_at_utc: string | null }
export type CandlePayload = { asset: Asset; symbol: string; resolution: '1m' | '5m' | '15m' | '1h'; data_state: string; candles: Candle[]; daily: { state: string; session_date_utc: string; open: number | null; previous_close: number | null; high: number | null; low: number | null; latest_close: number | null; change: number | null; change_percent: number | null }; warning: string }

export const time = (value?: string | null) => value ? new Date(value).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour12: true }) + ' IST' : 'Not recorded'
export const num = (value?: string | number | null) => value === null || value === undefined || !Number.isFinite(Number(value)) ? '—' : Number(value).toLocaleString('en-US', { maximumFractionDigits: 6 })
export const usd = (value?: string | number | null) => value === null || value === undefined ? '—' : '$' + num(value)
export const label = (value: string) => value.replaceAll('_', ' ')

export async function readJson<T>(url: string, signal: AbortSignal, accepted = [200]): Promise<T> {
  const response = await fetch(url, { cache: 'no-store', signal })
  if (!accepted.includes(response.status)) throw new Error(response.status === 401 ? 'Authentication required' : 'HTTP ' + response.status + ' for ' + url)
  return response.json() as Promise<T>
}

// One request at a time. Failed reads discard earlier data so stale values are never presented as current.
export function usePolling<T>(url: string, interval = 15000, accepted = [200]) {
  const [result, setResult] = useState<{ url: string; data: T | null; error: string | null }>({ url, data: null, error: null })
  useEffect(() => {
    const controller = new AbortController()
    let timer: number | undefined
    let alive = true
    setResult({ url, data: null, error: null })
    const load = async () => {
      try {
        const data = await readJson<T>(url, controller.signal, accepted)
        if (alive) setResult({ url, data, error: null })
      } catch (error) {
        if (alive) setResult({ url, data: null, error: error instanceof Error ? error.message : 'Request failed' })
      } finally {
        if (alive) timer = window.setTimeout(() => void load(), interval)
      }
    }
    void load()
    return () => { alive = false; controller.abort(); window.clearTimeout(timer) }
  }, [url, interval, accepted.join(',')])
  return result.url === url ? result : { url, data: null, error: null }
}
