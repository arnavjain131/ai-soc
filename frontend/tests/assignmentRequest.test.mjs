import assert from 'node:assert/strict'
import test from 'node:test'
import {prepareAssignmentRequest} from '../src/assignmentRequest.ts'
import {emptyIncidentFilters,incidentFilterParams} from '../src/incidentFilters.ts'
const user='11111111-1111-4111-8111-111111111111',revision='22222222-2222-4222-8222-222222222222'
test('lost assignment response retries reuse the UUID and original revision',()=>{
  const first=prepareAssignmentRequest(user,revision,null,()=> 'same-request')
  assert.equal(prepareAssignmentRequest(user,revision,first,()=>{throw new Error('must not allocate')}),first)
  const changed=prepareAssignmentRequest(null,revision,first,()=> 'new-request')
  assert.equal(changed.request_id,'new-request');assert.equal(changed.assignee_id,null)
  assert.notEqual(prepareAssignmentRequest(user,null,first,()=> 'fresh-revision').request_id,first.request_id)
})
test('assignment UUID validation happens before allocating a write request',()=>{
  assert.throws(()=>prepareAssignmentRequest('bad',null,null,()=>{throw new Error('must not allocate')}),/complete member/)
  assert.throws(()=>prepareAssignmentRequest(user,'bad',null,()=> 'unused'),/complete member/)
})
test('assignee filters preserve named modes and validate specific member IDs',()=>{
  for(const mode of ['me','unassigned','inactive'])assert.equal(incidentFilterParams({...emptyIncidentFilters,assignee:mode}).assignee,mode)
  assert.equal(incidentFilterParams({...emptyIncidentFilters,assignee:'member',assignee_id:user}).assignee,user)
  assert.throws(()=>incidentFilterParams({...emptyIncidentFilters,assignee:'member',assignee_id:'short'}),/complete member/)
})
