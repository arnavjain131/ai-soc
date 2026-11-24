import assert from 'node:assert/strict'
import test from 'node:test'
import { recoverAIRequest } from '../src/aiRequestRecovery.ts'

test('lost generation response recovers the original saved result and quota with reads only', async () => {
  const snapshots = [
    {latest:{id:'older'},quota:1,request:{state:'pending'}},
    {latest:{id:'saved'},quota:1,request:{state:'completed',analysis:{id:'saved'}}},
  ]
  const seen=[], waits=[]
  let reads=0
  const result=await recoverAIRequest(async()=>{reads++;return snapshots.shift()},s=>seen.push(s),()=>true,async ms=>waits.push(ms))
  assert.equal(result,'completed')
  assert.equal(reads,2)
  assert.equal(seen.at(-1).request.analysis.id,'saved')
  assert.equal(seen.at(-1).quota,1)
  assert.deepEqual(waits,[1000])
})

test('an unrelated latest analysis never counts as completion of this request',async()=>{
  let reads=0
  const result=await recoverAIRequest(async()=>{reads++;return {latest:{id:'other'},request:{state:'not_found'}}},()=>{},()=>true,async()=>{})
  assert.equal(result,'unconfirmed')
  assert.equal(reads,6)
})

test('transient GET errors recover and a recorded provider failure stops checking',async()=>{
  let reads=0
  const result=await recoverAIRequest(async()=>{if(++reads===1)throw new TypeError('Failed to fetch');return {request:{state:'failed'}}},()=>{},()=>true,async()=>{})
  assert.equal(result,'failed')
  assert.equal(reads,2)
})

test('membership denial stops recovery immediately',async()=>{
  let reads=0
  await assert.rejects(()=>recoverAIRequest(async()=>{reads++;throw Object.assign(new Error('Access revoked'),{status:403})},()=>{},()=>true,async()=>{}),/Access revoked/)
  assert.equal(reads,1)
})

test('leaving the incident cancels polling and discards in-flight results',async()=>{
  let active=true,seen=0
  const result=await recoverAIRequest(async()=>{active=false;return {request:{state:'completed',analysis:{id:'old'}}}},()=>{seen++},()=>active,async()=>{})
  assert.equal(result,'cancelled')
  assert.equal(seen,0)
})

test('cache-hit receipt recovers even if its saved analysis predates this request',async()=>{
  const result=await recoverAIRequest(async()=>({request:{state:'completed',analysis:{id:'existing-cache'}}}),()=>{},()=>true,async()=>{})
  assert.equal(result,'completed')
})
