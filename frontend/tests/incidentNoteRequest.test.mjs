import assert from 'node:assert/strict'
import test from 'node:test'
import { prepareNoteRequest } from '../src/incidentNoteRequest.ts'

test('a retry of unchanged text reuses its idempotency request ID', () => {
  const first = prepareNoteRequest('  Evidence reviewed.  ', null, () => 'first')
  assert.deepEqual(first, { body: 'Evidence reviewed.', request_id: 'first' })
  const retry = prepareNoteRequest('Evidence reviewed.', first, () => { throw new Error('must not generate another ID') })
  assert.equal(retry, first)
})
test('editing the note after an error creates a distinct request', () => {
  assert.deepEqual(prepareNoteRequest('Updated findings.', { body: 'Original.', request_id: 'old' }, () => 'new'),
    { body: 'Updated findings.', request_id: 'new' })
})
test('empty and oversized notes are rejected without allocating a request ID', () => {
  const never = () => { throw new Error('must not allocate') }
  assert.throws(() => prepareNoteRequest(' \n ', null, never), /Enter a note/)
  assert.throws(() => prepareNoteRequest('x'.repeat(2001), null, never), /2,000/)
})
