import assert from 'node:assert/strict'
import test from 'node:test'
import { sourceFreshness, receiptAge, STALE_AFTER_MS } from '../src/sourceHealth.ts'

const now = Date.parse('2026-11-22T00:00:00Z')
const source = { id: 'test', name: 'Lab', enabled: true, last_seen: null }
const seen = age => ({ ...source, last_seen: new Date(now - age).toISOString() })

test('freshness switches exactly at 15 minutes without claiming offline status', () => {
  assert.equal(sourceFreshness(seen(STALE_AFTER_MS - 1), now), 'recent')
  assert.equal(sourceFreshness(seen(STALE_AFTER_MS), now), 'stale')
  assert.equal(sourceFreshness(seen(7 * 86400000), now), 'stale')
})
test('never-received and revoked sources remain distinct', () => {
  assert.equal(sourceFreshness(source, now), 'never')
  assert.equal(sourceFreshness({ ...source, enabled: false }, now), 'revoked')
  assert.equal(sourceFreshness({ ...seen(0), enabled: false }, now), 'revoked')
})
test('invalid and materially future timestamps require review', () => {
  assert.equal(sourceFreshness({ ...source, last_seen: 'invalid' }, now), 'unknown')
  assert.equal(sourceFreshness(seen(-121000), now), 'unknown')
  assert.equal(sourceFreshness(seen(-30000), now), 'recent')
})
test('UTC and IST representations identify the same recent receipt', () => {
  const utc = { ...source, last_seen: '2026-11-21T23:55:00Z' }
  const ist = { ...source, last_seen: '2026-11-22T05:25:00+05:30' }
  assert.equal(sourceFreshness(utc, now), 'recent')
  assert.equal(sourceFreshness(ist, now), 'recent')
  assert.equal(receiptAge(utc.last_seen, now), receiptAge(ist.last_seen, now))
})
test('age labels cover seconds, minutes, hours, days and invalid values', () => {
  assert.equal(receiptAge(seen(30000).last_seen, now), 'Less than a minute ago')
  assert.equal(receiptAge(seen(5 * 60000).last_seen, now), '5 min ago')
  assert.equal(receiptAge(seen(2 * 3600000).last_seen, now), '2 hr ago')
  assert.equal(receiptAge(seen(2 * 86400000).last_seen, now), '2 days ago')
  assert.equal(receiptAge('invalid', now), 'Unknown time')
})
