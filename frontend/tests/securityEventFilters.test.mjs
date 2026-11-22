import assert from 'node:assert/strict'
import test from 'node:test'
import { securityFilterParams, emptySecurityFilters } from '../src/securityEventFilters.ts'

test('empty filters impose no default time range', () => {
  assert.deepEqual(securityFilterParams(emptySecurityFilters), {})
})
test('text filters remain literal and trim surrounding whitespace', () => {
  const result = securityFilterParams({ ...emptySecurityFilters, username: ' alice%_ ', source_ip: ' 10.0.2.2 ' })
  assert.deepEqual(result, { username: 'alice%_', source_ip: '10.0.2.2' })
  assert.equal(new URLSearchParams(result).get('username'), 'alice%_')
})
test('local date inputs are converted to explicit UTC', () => {
  const local = '2026-11-22T05:13:00'
  assert.equal(securityFilterParams({ ...emptySecurityFilters, start_time: local }).start_time, new Date(local).toISOString())
})
test('invalid and reversed time ranges fail before requesting events', () => {
  assert.throws(() => securityFilterParams({ ...emptySecurityFilters, start_time: 'invalid' }), /valid start/)
  assert.throws(() => securityFilterParams({ ...emptySecurityFilters, start_time: '2026-11-23T00:00', end_time: '2026-11-22T00:00' }), /Start time/)
})
