import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { runInNewContext } from 'node:vm'
import ts from 'typescript'

// Execute the actual TypeScript presentation helpers, without a browser or a
// second copy of their implementation. All fixture identities/prices are hypothetical.
const source = readFileSync(new URL('../src/format.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, {
  fileName: 'format.ts',
  reportDiagnostics: true,
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
})
assert.equal(compiled.diagnostics?.filter(item => item.category === ts.DiagnosticCategory.Error).length, 0)
const loaded = { exports: {} }
runInNewContext(compiled.outputText, { module: loaded, exports: loaded.exports }, { filename: 'format.ts', timeout: 1000 })
const { assessmentMatches, lifecycle, valueOf, number, price, when, age, isSweep } = loaded.exports

const NOW = Date.parse('2026-11-22T10:00:00Z')

function entryFixture() {
  return {
    candidate: {
      candidate_id: 'hypothetical-gold-fast-candidate',
      snapshot_id: 'a'.repeat(64),
      asset: 'GOLD', symbol: 'XAUTUSD', venue: 'delta_india', engine: 'GOLD_FAST',
      horizon_minutes: 30, direction: 'BULLISH',
      candle_close_utc: '2026-11-22T09:59:00Z',
      observed_at_utc: '2026-11-22T10:00:00Z',
      expires_at_utc: '2026-11-22T10:30:00Z',
      trigger: '1m liquidity sweep and closed-candle reclaim',
      entry: 2600.10, invalidation: 2595, targets: [2610.10, 2620.10],
      feature_evidence: ['Hypothetical presentation fixture'], counter_evidence: [],
      source_quality: 'VALID', rule_version: 'hypothetical-test',
    },
    candidate_revision_id: 'b'.repeat(64),
    consensus: { status: 'CONFIRMED', reason: 'Hypothetical historical review, not a current signal.' },
    current_lifecycle_state: 'CANDIDATE', current_lifecycle_reason: null,
    current_lifecycle_at_utc: '2026-11-22T10:00:00Z',
    review: {
      run_id: 'hypothetical-review-run', status: 'COMPLETED',
      created_at_utc: '2026-11-22T10:00:00Z', deadline_at_utc: '2026-11-22T10:00:30Z',
      envelope_digest: 'c'.repeat(64), attempts: [],
    },
  }
}

function assessmentFixture(entry) {
  return {
    candidate_id: entry.candidate.candidate_id,
    candidate_revision_id: entry.candidate_revision_id,
    snapshot_id: entry.candidate.snapshot_id,
    analysis_input_hash: entry.review.envelope_digest,
    asset: entry.candidate.asset, symbol: entry.candidate.symbol,
    engine: entry.candidate.engine, horizon_minutes: entry.candidate.horizon_minutes,
    direction: entry.candidate.direction,
    decision: 'CONFIRM', supported_target_indices: [1],
    reason: 'Hypothetical provider packet; no real provider was called.',
    counter_evidence: [], data_warnings: ['Synthetic presentation test only'],
  }
}

test('a complete provider packet matches only its selected candidate and frozen evidence', () => {
  const entry = entryFixture()
  assert.equal(assessmentMatches(entry, assessmentFixture(entry)), true)

  const bitcoin = entryFixture()
  Object.assign(bitcoin.candidate, {
    candidate_id: 'hypothetical-bitcoin-hourly-candidate', snapshot_id: 'd'.repeat(64),
    asset: 'BTC', symbol: 'BTCUSD', engine: 'BTC_HOURLY', horizon_minutes: 60,
    direction: 'BEARISH',
  })
  bitcoin.candidate_revision_id = 'e'.repeat(64)
  bitcoin.review.envelope_digest = 'f'.repeat(64)
  assert.equal(assessmentMatches(bitcoin, assessmentFixture(bitcoin)), true)
  assert.equal(assessmentMatches(bitcoin, assessmentFixture(entry)), false)
})

const foreignIdentities = {
  candidate_id: 'another-hypothetical-candidate',
  candidate_revision_id: 'd'.repeat(64),
  snapshot_id: 'e'.repeat(64),
  analysis_input_hash: 'f'.repeat(64),
  asset: 'BTC', symbol: 'BTCUSD', engine: 'GOLD_HOURLY',
  horizon_minutes: 60, direction: 'BEARISH',
}
for (const [field, foreignValue] of Object.entries(foreignIdentities)) {
  test(`provider identity ${field}: missing field cannot approve`, () => {
    const entry = entryFixture()
    const assessment = assessmentFixture(entry)
    delete assessment[field]
    assert.equal(assessmentMatches(entry, assessment), false)
  })
  test(`provider identity ${field}: a different value cannot approve`, () => {
    const entry = entryFixture()
    const assessment = { ...assessmentFixture(entry), [field]: foreignValue }
    assert.equal(assessmentMatches(entry, assessment), false)
  })
}

test('missing review, digest, revision or assessment withholds provider identity acceptance', () => {
  const entry = entryFixture()
  const assessment = assessmentFixture(entry)
  assert.equal(assessmentMatches(null, assessment), false)
  assert.equal(assessmentMatches(entry, null), false)
  assert.equal(assessmentMatches(entry, undefined), false)
  assert.equal(assessmentMatches({ ...entry, review: null }, assessment), false)
  assert.equal(assessmentMatches({ ...entry, review: { ...entry.review, envelope_digest: '' } }, assessment), false)
  assert.equal(assessmentMatches({ ...entry, candidate_revision_id: '' }, assessment), false)
})

for (const state of ['INVALIDATED', 'REJECTED', 'EXPIRED']) {
  test(`historical CONFIRMED never promotes ${state} lifecycle`, () => {
    const entry = { ...entryFixture(), current_lifecycle_state: state }
    assert.equal(lifecycle(entry, NOW), state)
    assert.equal(lifecycle(entry, NOW + 60 * 60 * 1000), state)
  })
}

test('an unexpired candidate remains CANDIDATE, not its historical CONFIRMED review', () => {
  assert.equal(lifecycle(entryFixture(), NOW), 'CANDIDATE')
})

test('candidate expiry applies at the exact boundary and after it', () => {
  const entry = entryFixture()
  const expiry = Date.parse(entry.candidate.expires_at_utc)
  assert.equal(lifecycle(entry, expiry - 1), 'CANDIDATE')
  assert.equal(lifecycle(entry, expiry), 'EXPIRED')
  assert.equal(lifecycle(entry, expiry + 1), 'EXPIRED')
})

test('missing or invalid expiry cannot present an active candidate', () => {
  for (const expires_at_utc of [undefined, null, '', 'not-a-timestamp']) {
    const entry = entryFixture()
    entry.candidate.expires_at_utc = expires_at_utc
    assert.equal(lifecycle(entry, NOW), 'UNKNOWN', String(expires_at_utc))
  }
  const missing = entryFixture()
  delete missing.candidate.expires_at_utc
  assert.equal(lifecycle(missing, NOW), 'UNKNOWN')
})

test('absent candidate or lifecycle remains UNKNOWN despite historical confirmation', () => {
  assert.equal(lifecycle(null, NOW), 'UNKNOWN')
  assert.equal(lifecycle(undefined, NOW), 'UNKNOWN')
  assert.equal(lifecycle({ ...entryFixture(), current_lifecycle_state: null }, NOW), 'UNKNOWN')
})

test('missing and invalid numeric values render unavailable rather than zero', () => {
  for (const value of [undefined, null, '', '   ', '\t', 'not-a-number', '1,234.50', NaN, Infinity, -Infinity, 'Infinity']) {
    assert.equal(valueOf(value), null, `valueOf(${String(value)})`)
    assert.equal(number(value), '—', `number(${String(value)})`)
    assert.equal(price(value), '—', `price(${String(value)})`)
  }
})

test('real numeric zero and Decimal-style money strings retain their recorded values', () => {
  for (const value of [0, '0', '0.00']) {
    assert.equal(valueOf(value), 0)
    assert.equal(number(value), '0')
    assert.equal(price(value), '$0.00')
  }
  assert.equal(valueOf('2600.10'), 2600.1)
  assert.equal(price('2600.10'), '$2,600.10')
  assert.equal(price('70000.50'), '$70,000.50')
  assert.equal(number('-1250.50'), '-1,250.5')
  assert.equal(price('0.000123'), '$0.000123')
})

test('missing and invalid timestamps are not presented as current observations', () => {
  for (const value of [undefined, null, '', ' ', 'not-a-timestamp']) {
    assert.equal(age(value, NOW), 'No timestamp')
    assert.equal(when(value, 'UTC'), 'Not recorded')
    assert.equal(when(value, 'Asia/Kolkata', true), 'Not recorded')
  }
  assert.equal(age('2026-11-22T10:01:00Z', NOW), 'Timestamp ahead')
  assert.equal(age('2026-11-22T09:58:00Z', NOW), '2m ago')
})

test('a recorded UTC timestamp converts to the selected display timezone', () => {
  const observed = '2026-11-22T10:00:00Z'
  assert.equal(when(observed, 'UTC'), '10:00:00 UTC')
  assert.equal(when(observed, 'Asia/Kolkata'), '15:30:00 IST')
})

test('sweep filtering accepts recorded sweep triggers and excludes breakout/structure triggers', () => {
  const entry = entryFixture()
  for (const trigger of ['1m liquidity sweep and closed-candle reclaim', '3m LIQUIDITY SWEEP and closed-candle reclaim']) {
    assert.equal(isSweep({ ...entry, candidate: { ...entry.candidate, trigger } }), true, trigger)
  }
  for (const trigger of ['5m breakout and retest', 'Higher-timeframe market structure break', 'Broad sweeping price movement']) {
    assert.equal(isSweep({ ...entry, candidate: { ...entry.candidate, trigger } }), false, trigger)
  }
})
