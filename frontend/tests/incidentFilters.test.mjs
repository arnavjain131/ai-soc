import assert from 'node:assert/strict'
import test from 'node:test'
import {demoIncidentPage,emptyIncidentFilters,incidentFilterParams} from '../src/incidentFilters.ts'

const rows=Array.from({length:33},(_,i)=>({id:`incident-${String(i).padStart(2,'0')}`,title:i===1?'Literal %_sensor':'Fixture '+i,
  status:i%2?'closed':'open',severity:i%2?'medium':'high',risk_score:i,score_components:{},
  created_at:new Date(Date.UTC(2026,0,1,0,i)).toISOString(),updated_at:'2026-01-01T00:00:00Z',alerts:[{rule_key:i%2?'brute_force_v1':'tcp_port_scan_v1'}]}))
const request={params:{sort:'newest'},offset:0,limit:10,asOf:'2026-01-02T00:00:00Z'}

test('queue filters preserve literal search and convert local creation bounds to UTC',()=>{
  const params=incidentFilterParams({...emptyIncidentFilters,q:' %_sensor ',start_time:'2026-01-01T05:30:00+05:30',end_time:'2026-01-01T06:30:00+05:30',status:'open'})
  assert.deepEqual(params,{sort:'newest',q:'%_sensor',status:'open',start_time:'2026-01-01T00:00:00.000Z',end_time:'2026-01-01T01:00:00.000Z'})
  assert.deepEqual(incidentFilterParams(emptyIncidentFilters),{sort:'newest'})
  assert.throws(()=>incidentFilterParams({...emptyIncidentFilters,start_time:'invalid'}),/valid/)
  assert.throws(()=>incidentFilterParams({...emptyIncidentFilters,start_time:'2026-01-02',end_time:'2026-01-01'}),/must not/)
})

test('demo pagination counts all matches and navigates without losing its snapshot',()=>{
  const first=demoIncidentPage(rows,request)
  const second=demoIncidentPage(rows,{...request,offset:10,asOf:first.as_of})
  assert.equal(first.total,33);assert.equal(first.items.length,10);assert.equal(first.has_more,true)
  assert.equal(new Set([...first.items,...second.items].map(r=>r.id)).size,20)
  assert.deepEqual(first.items.map(r=>r.id),rows.slice(-10).reverse().map(r=>r.id))
  const last=demoIncidentPage(rows,{...request,offset:30})
  assert.equal(last.items.length,3);assert.equal(last.has_more,false)
})

test('demo literal search, combined detection filters, dates and risk order match queue semantics',()=>{
  assert.equal(demoIncidentPage(rows,{...request,params:{q:'%_'}}).total,1)
  assert.equal(demoIncidentPage(rows,{...request,params:{status:'open',severity:'high',rule_key:'tcp_port_scan_v1'}}).total,17)
  assert.equal(demoIncidentPage(rows,{...request,params:{start_time:rows[0].created_at,end_time:rows[0].created_at}}).total,1)
  assert.equal(demoIncidentPage(rows,{...request,params:{sort:'risk'}}).items[0].risk_score,32)
  assert.equal(demoIncidentPage(rows,{...request,params:{sort:'oldest'}}).items[0].id,rows[0].id)
})
