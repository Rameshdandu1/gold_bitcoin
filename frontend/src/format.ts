import type { Assessment, CandidateEntry, Numeric, Timezone } from './types'

export function valueOf(value: Numeric | undefined): number | null {
  if (value === null || value === undefined || (typeof value === 'string' && value.trim() === '')) return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

export function number(value: Numeric | undefined, digits = 2): string {
  const parsed = valueOf(value)
  return parsed === null ? '—' : parsed.toLocaleString('en-US', { maximumFractionDigits: digits })
}

export function price(value: Numeric | undefined): string {
  const parsed = valueOf(value)
  return parsed === null ? '—' : parsed.toLocaleString('en-US', {
    style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: parsed < 1 ? 6 : 2,
  })
}

export function when(value: string | null | undefined, timezone: Timezone, withDate = false): string {
  if (!value || !Number.isFinite(Date.parse(value))) return 'Not recorded'
  return new Intl.DateTimeFormat('en-GB', {
    timeZone: timezone, hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
    ...(withDate ? { day: '2-digit', month: 'short' } as const : {}),
  }).format(new Date(value)) + (timezone === 'UTC' ? ' UTC' : ' IST')
}

export function age(value: string | null | undefined, now: number): string {
  if (!value || !Number.isFinite(Date.parse(value))) return 'No timestamp'
  const seconds = Math.floor((now - Date.parse(value)) / 1000)
  if (seconds < -5) return 'Timestamp ahead'
  if (seconds < 5) return 'Just now'
  if (seconds < 60) return seconds + 's ago'
  if (seconds < 3600) return Math.floor(seconds / 60) + 'm ago'
  if (seconds < 86400) return Math.floor(seconds / 3600) + 'h ago'
  return Math.floor(seconds / 86400) + 'd ago'
}

export function label(value: string | null | undefined): string {
  return value ? value.toLowerCase().replace(/_/g, ' ').replace(/\b\w/g, letter => letter.toUpperCase()) : 'Not recorded'
}

/** Presentation only: never promotes a historical confirmation to a current signal. */
export function lifecycle(entry: CandidateEntry | null | undefined, now: number): string {
  if (!entry?.current_lifecycle_state) return 'UNKNOWN'
  if (entry.current_lifecycle_state !== 'CANDIDATE') return entry.current_lifecycle_state
  const expiry = Date.parse(entry.candidate.expires_at_utc)
  if (!Number.isFinite(expiry)) return 'UNKNOWN'
  return now >= expiry ? 'EXPIRED' : 'CANDIDATE'
}

export function isSweep(entry: CandidateEntry): boolean {
  return /\bsweep\b/i.test(entry.candidate.trigger)
}

/** Withhold a provider verdict unless every echoed identity matches this evidence packet. */
export function assessmentMatches(entry: CandidateEntry | null, assessment: Assessment | null | undefined): boolean {
  if (!entry?.review || !assessment || !entry.review.envelope_digest || !entry.candidate_revision_id) return false
  const candidate = entry.candidate
  return assessment.candidate_id === candidate.candidate_id
    && assessment.candidate_revision_id === entry.candidate_revision_id
    && assessment.snapshot_id === candidate.snapshot_id
    && assessment.analysis_input_hash === entry.review.envelope_digest
    && assessment.asset === candidate.asset
    && assessment.symbol === candidate.symbol
    && assessment.engine === candidate.engine
    && assessment.horizon_minutes === candidate.horizon_minutes
    && assessment.direction === candidate.direction
}
