import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { ArrowDownRight, ShieldAlert } from 'lucide-react'
import { api, ApiError } from './api'
import { demoIncidents } from './demo'
import { demoIncidentPage, emptyIncidentFilters, incidentFilterParams, type IncidentFilters, type IncidentPage, type QueueView } from './incidentFilters'
import type { Incident } from './types'
import './incidentQueue.css'

const rules=[['brute_force_v1','SSH brute force'],['password_spray_v1','Password spraying'],['tcp_port_scan_v1','TCP port scan'],['suricata_priority_alert_v1','Priority Suricata alert']]
const label=(value:string)=>value.replaceAll('_',' ')
export function IncidentQueue({mode,view,onViewChange,onOpen,disabled}:{mode:'demo'|'private';view:QueueView;onViewChange:(value:QueueView)=>void;onOpen:(incident:Incident)=>void;disabled:boolean}) {
  const [page,setPage]=useState<IncidentPage|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState(''),[formError,setFormError]=useState('')
  const [retry,setRetry]=useState(0)
  const request=view.request
  useEffect(()=>{
    let active=true
    setPage(null);setLoading(true);setError('')
    async function load() {
      try {
        const params=new URLSearchParams({...request.params,limit:String(request.limit),offset:String(request.offset)})
        if(request.asOf)params.set('as_of',request.asOf)
        const result=mode==='demo' ? demoIncidentPage(demoIncidents,request) : await api<IncidentPage>(`/api/incidents/search?${params}`)
        if(active)setPage(result)
      } catch(failure) {
        if(active)setError(failure instanceof ApiError && failure.status===404 ? 'Incident search requires the latest backend deployment.' : failure instanceof Error ? failure.message : 'Could not load incidents.')
      } finally {if(active)setLoading(false)}
    }
    void load()
    return ()=>{active=false}
  },[request,mode,retry])
  function update(key:keyof IncidentFilters,value:string) {onViewChange({...view,draft:{...view.draft,[key]:value}})}
  function apply(event:FormEvent) {
    event.preventDefault()
    try {const params=incidentFilterParams(view.draft);setFormError('');onViewChange({...view,request:{params,offset:0,limit:request.limit}})}
    catch(failure){setFormError(failure instanceof Error ? failure.message : 'Check the filters.')}
  }
  function move(offset:number) {if(page)onViewChange({...view,request:{...request,offset,asOf:page.as_of}})}
  return <section className="panel queue incident-queue">
    <div className="panel-heading"><div><h2>Incident queue</h2><p>{mode==='demo' ? 'Search fixed demonstration incidents.' : 'Search all incidents in your private workspace.'}</p></div></div>
    <form className="incident-filters" onSubmit={apply}>
      <label className="incident-search">Title or incident ID<input aria-label="Search incidents" placeholder="Search title or ID…" maxLength={200} value={view.draft.q} onChange={e=>update('q',e.target.value)}/></label>
      <label>Status<select value={view.draft.status} onChange={e=>update('status',e.target.value)}><option value="">All statuses</option>{['open','investigating','closed','false_positive'].map(value=><option key={value} value={value}>{label(value)}</option>)}</select></label>
      <label>Severity<select value={view.draft.severity} onChange={e=>update('severity',e.target.value)}><option value="">All severities</option>{['critical','high','medium','low'].map(value=><option key={value} value={value}>{value}</option>)}</select></label>
      <label>Detection<select value={view.draft.rule_key} onChange={e=>update('rule_key',e.target.value)}><option value="">All detections</option>{rules.map(([value,text])=><option key={value} value={value}>{text}</option>)}</select></label>
      {mode==='private' && <><label>Assignee<select value={view.draft.assignee} onChange={e=>update('assignee',e.target.value)}><option value="">All owners</option><option value="me">Assigned to me</option><option value="unassigned">Unassigned</option><option value="inactive">Inactive owner</option><option value="member">Specific member</option></select></label>
        {view.draft.assignee==='member' && <label>Member account UUID<input value={view.draft.assignee_id} maxLength={36} onChange={e=>update('assignee_id',e.target.value)} placeholder="Complete account UUID"/></label>}</>}
      <label>Created from (local time)<input type="datetime-local" step="1" value={view.draft.start_time} onChange={e=>update('start_time',e.target.value)}/></label>
      <label>Created to (local time)<input type="datetime-local" step="1" value={view.draft.end_time} onChange={e=>update('end_time',e.target.value)}/></label>
      <label>Sort by<select value={view.draft.sort} onChange={e=>update('sort',e.target.value)}><option value="newest">Newest first</option><option value="oldest">Oldest first</option><option value="risk">Highest risk first</option></select></label>
      <div className="incident-filter-actions"><button className="primary" disabled={loading}>Apply filters</button><button type="button" className="secondary" disabled={loading} onClick={()=>{setFormError('');onViewChange({draft:{...emptyIncidentFilters},request:{params:{sort:'newest'},offset:0,limit:request.limit}})}}>Clear</button></div>
    </form>
    {formError && <p className="queue-feedback login-error" role="alert">{formError}</p>}
    {error && <div className="queue-feedback" role="alert"><p className="login-error">{error}</p><button className="secondary" onClick={()=>setRetry(value=>value+1)}>Retry queue</button></div>}
    {loading && <p className="queue-feedback" role="status">Loading incidents…</p>}
    {!loading && page && <>
      <p className="queue-feedback" role="status">{page.items.length ? `${page.offset+1}–${page.offset+page.items.length} of ${page.total} matching incidents` : page.total ? 'This page is empty. Return to the previous page or refresh the queue.' : 'No incidents match these filters.'}</p>
      {!!page.items.length && <div className="table-wrap"><table><thead><tr><th>INCIDENT</th><th>SEVERITY</th><th>STATUS</th><th>RISK</th>{mode==='private' && <th>ASSIGNEE</th>}<th><span className="sr-only">Open</span></th></tr></thead><tbody>{page.items.map(item=><tr key={item.id}>
        <td><button className="incident-link" disabled={disabled} onClick={()=>onOpen(item)}><span className="incident-symbol"><ShieldAlert size={18}/></span><span>{item.title}<small><time dateTime={item.created_at} title={item.created_at}>{new Date(item.created_at).toLocaleString(undefined,{timeZoneName:'short'})}</time></small></span></button></td>
        <td><span className="severity">{item.severity}</span></td><td><span className={`status ${item.status}`}><span/>{label(item.status)}</span></td><td><strong className="risk-cell">{item.risk_score}</strong><span className="muted"> /100</span></td>
        {mode==='private' && <td><span title={item.assignment?.assignee_id||undefined}>{!item.assignment?.assignee_id?'Unassigned':`${item.assignment.active ? item.assignment.is_self?'You':'Member' : 'Inactive'} · ${item.assignment.assignee_id.slice(0,8)}`}</span></td>}
        <td><button className="icon-button" disabled={disabled} aria-label={`Investigate ${item.title}`} onClick={()=>onOpen(item)}><ArrowDownRight size={18}/></button></td>
      </tr>)}</tbody></table></div>}
      <div className="incident-pagination"><label>Per page<select aria-label="Incidents per page" value={request.limit} onChange={e=>onViewChange({...view,request:{...request,limit:Number(e.target.value),offset:0,asOf:undefined}})}>{[10,25,50,100].map(n=><option key={n} value={n}>{n}</option>)}</select></label>
        <button className="secondary" disabled={!page.offset} onClick={()=>move(Math.max(0,page.offset-page.limit))}>Previous</button><button className="secondary" disabled={!page.has_more} onClick={()=>move(page.offset+page.limit)}>Next</button>
      </div><p className="queue-feedback small muted">Creation times use your local timezone. Paging excludes newly created incidents after this queue snapshot; refresh to include them. Status and risk changes can still move results.</p>
    </>}
  </section>
}
