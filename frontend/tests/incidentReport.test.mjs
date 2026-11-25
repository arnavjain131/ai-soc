import assert from 'node:assert/strict'
import test from 'node:test'
import {reportRequest} from '../src/reportDownload.ts'
const id='11111111-2222-4333-8444-555555555555'
test('report download uses a private ID, explicit format and AI inclusion without credentials in URL',()=>{
  assert.deepEqual(reportRequest(id,'html',true),{path:`/api/incidents/${id}/report?format=html&include_ai=true`,filename:`aisoc-incident-${id}.html`})
  assert.deepEqual(reportRequest(id,'json',false),{path:`/api/incidents/${id}/report?format=json&include_ai=false`,filename:`aisoc-incident-${id}.json`})
})
test('download filenames never use untrusted incident titles, paths or demo IDs',()=>{
  for(const invalid of ['demo-auth-001','../private','x\r\nContent-Disposition:evil'])assert.throws(()=>reportRequest(invalid,'html',true),/private incident/)
  assert.throws(()=>reportRequest(id,'exe',true),/HTML or JSON/)
})
