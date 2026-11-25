import {useEffect,useRef,useState} from 'react'
import {api,ApiError} from './api'
import {prepareAssignmentRequest,type AssignmentRequest} from './assignmentRequest'
import type {Assignment} from './types'
import './incidentAssignment.css'

type Candidate={user_id:string;role:string;is_self:boolean}
type CandidatePage={items:Candidate[];offset:number;limit:number;has_more:boolean;total:number}
export function IncidentAssignment({incidentId,viewerId,refreshKey,onChanged}:{incidentId:string;viewerId?:string;refreshKey:string;onChanged:()=>void}) {
  const [current,setCurrent]=useState<Assignment|null>(null),[selected,setSelected]=useState(''),[candidates,setCandidates]=useState<Candidate[]>([])
  const [page,setPage]=useState<CandidatePage|null>(null),[loading,setLoading]=useState(true),[saving,setSaving]=useState(false),[more,setMore]=useState(false)
  const [error,setError]=useState(''),[notice,setNotice]=useState(''),[conflict,setConflict]=useState(false),[revision,setRevision]=useState(0)
  const version=useRef(0),pending=useRef<AssignmentRequest|null>(null),submitting=useRef(false)
  const path=`/api/incidents/${incidentId}/assignment`
  useEffect(()=>{
    const request=++version.current
    setLoading(true);setCurrent(null);setError('');setNotice('');setCandidates([]);setPage(null);setConflict(false)
    void Promise.all([api<Assignment>(path),api<CandidatePage>('/api/assignment-candidates?limit=50')]).then(([assignment,people])=>{
      if(version.current!==request)return
      setCurrent(assignment);setSelected(assignment.assignee_id||'');setCandidates(people.items);setPage(people);pending.current=null
    }).catch(failure=>{if(version.current===request)setError(failure instanceof Error?failure.message:'Could not load ownership.')})
      .finally(()=>{if(version.current===request)setLoading(false)})
    return ()=>{version.current++}
  },[incidentId,refreshKey,revision])
  async function loadMore() {
    if(!page || !page.has_more || more)return
    const request=version.current
    setMore(true);setError('')
    try {
      const next=await api<CandidatePage>(`/api/assignment-candidates?limit=50&offset=${page.offset+page.limit}`)
      if(version.current!==request)return
      setCandidates(previous=>[...new Map([...previous,...next.items].map(member=>[member.user_id,member])).values()]);setPage(next)
    } catch(failure){if(version.current===request)setError(failure instanceof Error?failure.message:'Could not load members.')}
    finally {setMore(false)}
  }
  async function save() {
    if(!current || conflict || submitting.current)return
    const request=version.current
    let payload:AssignmentRequest
    try {payload=prepareAssignmentRequest(selected||null,current.revision,pending.current,()=>crypto.randomUUID())}
    catch(failure){setError(failure instanceof Error?failure.message:'Choose an approved member.');return}
    pending.current=payload;submitting.current=true;setSaving(true);setError('');setNotice('')
    try {
      const result=await api<{assignment:Assignment;replayed:boolean;changed:boolean}>(path,'PUT',payload)
      if(version.current!==request)return
      pending.current=null;setCurrent(result.assignment);setSelected(result.assignment.assignee_id||'')
      setNotice(result.replayed?'The request was already recorded. Current ownership has been refreshed.':result.changed?'Assignment saved to incident history.':'Ownership is unchanged.')
      onChanged()
    } catch(failure) {
      if(version.current!==request)return
      setConflict(failure instanceof ApiError && failure.status===409)
      setError((failure instanceof Error?failure.message:'Could not save assignment.')+(!(failure instanceof ApiError)?' Retrying the same selection preserves the request ID.':''))
    } finally {submitting.current=false;setSaving(false)}
  }
  const missing=selected && !candidates.some(member=>member.user_id===selected)
  return <section className="panel incident-assignment"><div className="panel-heading"><div><h2>Incident ownership</h2><p>Assign investigation responsibility to an approved workspace member. Assignment does not grant access or change incident status.</p></div></div>
    <div className="assignment-body">
      {loading && <p role="status">Loading ownership and approved members…</p>}
      {error && <p className="login-error" role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
      {current && <><p>Current owner: {current.assignee_id ? <span className="mono">{current.is_self?'You · ':''}{current.assignee_id}</span>:'Unassigned'}</p>
        {current.assignee_id && !current.active && <p role="status">This owner no longer has workspace access. Reassign or unassign this incident.</p>}
        <label>Assigned analyst<select disabled={saving||loading} value={selected} onChange={event=>{setSelected(event.target.value);setNotice('')}}><option value="">Unassigned</option>
          {missing && <option value={selected}>{selected===current.assignee_id?'Current owner':'Selected member'} · {selected}{selected===current.assignee_id && !current.active?' (inactive)':''}</option>}
          {candidates.map(member=><option key={member.user_id} value={member.user_id}>{member.is_self?'You':member.role} · {member.user_id}</option>)}
        </select></label>
        <p className="small muted">Account IDs identify members without exposing email addresses. Only approved admins and analysts are eligible.</p>
        <div className="assignment-actions"><button className="primary" disabled={saving||loading||conflict||(!pending.current && selected===(current.assignee_id||''))} onClick={()=>void save()}>{saving?'Saving assignment…':'Save assignment'}</button>
          {viewerId && <button className="secondary" disabled={saving||loading} onClick={()=>setSelected(viewerId)}>Select myself</button>}
          {page?.has_more && <button className="secondary" disabled={saving||loading||more} onClick={()=>void loadMore()}>{more?'Loading members…':'Load more members'}</button>}
        </div></>}
      <button className="secondary" disabled={saving||loading} onClick={()=>setRevision(value=>value+1)}>Refresh ownership</button>
    </div></section>
}
