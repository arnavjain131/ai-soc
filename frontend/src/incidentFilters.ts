import type { Incident } from './types'

export type IncidentFilters = {q:string;status:string;severity:string;rule_key:string;start_time:string;end_time:string;sort:string}
export const emptyIncidentFilters:IncidentFilters={q:'',status:'',severity:'',rule_key:'',start_time:'',end_time:'',sort:'newest'}
export type QueueRequest={params:Record<string,string>;offset:number;limit:number;asOf?:string}
export type QueueView={draft:IncidentFilters;request:QueueRequest}
export const initialQueueView:QueueView={draft:emptyIncidentFilters,request:{params:{sort:'newest'},offset:0,limit:25}}
export type IncidentPage={items:Incident[];total:number;offset:number;limit:number;has_more:boolean;as_of:string}

export function incidentFilterParams(filters:IncidentFilters):Record<string,string> {
  const params:Record<string,string>={sort:filters.sort}
  for(const key of ['q','status','severity','rule_key'] as const)if(filters[key].trim())params[key]=filters[key].trim()
  for(const key of ['start_time','end_time'] as const)if(filters[key]) {
    const time=new Date(filters[key])
    if(!Number.isFinite(time.getTime()))throw new Error('Enter valid creation times.')
    params[key]=time.toISOString()
  }
  if(params.start_time && params.end_time && params.start_time>params.end_time)throw new Error('From time must not be after To time.')
  return params
}

export function demoIncidentPage(rows:(Incident & {alerts?:{rule_key:string}[]})[],request:QueueRequest):IncidentPage {
  const p=request.params,cutoff=request.asOf||new Date().toISOString()
  const filtered=rows.filter(row=>(!p.q || row.title.toLowerCase().includes(p.q.toLowerCase()) || row.id.toLowerCase().includes(p.q.toLowerCase()))
    && (!p.status || row.status===p.status) && (!p.severity || row.severity.toLowerCase()===p.severity)
    && (!p.rule_key || row.alerts?.some(alert=>alert.rule_key===p.rule_key))
    && (!p.start_time || Date.parse(row.created_at)>=Date.parse(p.start_time))
    && (!p.end_time || Date.parse(row.created_at)<=Date.parse(p.end_time)) && Date.parse(row.created_at)<=Date.parse(cutoff))
  filtered.sort((a,b)=>(p.sort==='risk' ? b.risk_score-a.risk_score : 0)
    || (p.sort==='oldest' ? Date.parse(a.created_at)-Date.parse(b.created_at) : Date.parse(b.created_at)-Date.parse(a.created_at))
    || a.id.localeCompare(b.id))
  return {items:filtered.slice(request.offset,request.offset+request.limit),total:filtered.length,
    offset:request.offset,limit:request.limit,has_more:request.offset+request.limit<filtered.length,as_of:cutoff}
}
