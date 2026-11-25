import { useEffect, useRef, useState } from 'react'
import { api, ApiError } from './api'
import { aiFailureMessage, recoverAIRequest, type AIRequestReceipt } from './aiRequestRecovery'
import './incidentAI.css'

type Analysis = {
  id:string; generated_at:string; model:string; outdated:boolean; knowledge_version:string
  answer:{ summary:string; observations:{text:string;event_ids:string[]}[]; interpretation:string;
    investigation_steps:{text:string;reference_ids:string[]}[]; limitations:string[] }
  references:{id:string;title:string;url:string|null}[]; context_limitations:string[]
  omitted_linked_events:number; omitted_related_events:number
}
type State = {enabled:boolean;has_evidence:boolean;provider:string;model:string;
  quota:{daily_used:number;daily_limit:number;monthly_used:number;monthly_limit:number};latest:Analysis|null;
  request?:AIRequestReceipt<Analysis>|null}

export function IncidentAI({ incidentId, eventIds }: { incidentId:string; eventIds:string[] }) {
  const [state,setState]=useState<State|null>(null), [loading,setLoading]=useState(true), [busy,setBusy]=useState(false)
  const [error,setError]=useState(''), [notice,setNotice]=useState(''), [knownFailure,setKnownFailure]=useState(false)
  const [revision,setRevision]=useState(0)
  const pending=useRef<string|null>(null), submitting=useRef(false), current=useRef(0)
  const path=`/api/incidents/${incidentId}/ai-analysis`
  function acceptSnapshot(result:State) {
    if(pending.current && result.request?.state==='completed' && result.request.analysis) {
      pending.current=null
      setError('');setKnownFailure(false)
      setNotice('Saved AI analysis recovered automatically. No additional model call was made.')
      setState({...result,latest:result.request.analysis})
    } else {
      setState(result)
      if(result.request?.state==='failed') {
        setKnownFailure(true)
        setError(aiFailureMessage(result.request.error_code))
      }
    }
  }
  const evidenceVersion=eventIds.join(',')
  useEffect(() => {
    const request=++current.current
    setLoading(true);setError('')
    void api<State>(path+(pending.current ? `?request_id=${pending.current}` : '')).then(result => {
      if(current.current===request)acceptSnapshot(result)
    }).catch(failure => {
      if(current.current===request)setError(failure instanceof ApiError && failure.status===404
        ? 'AI analysis requires the latest backend deployment.' : failure instanceof Error ? failure.message : 'Could not load AI status.')
    }).finally(() => {if(current.current===request)setLoading(false)})
    return () => {current.current+=1}
  },[incidentId,revision,evidenceVersion])

  async function analyze(newAttempt=false) {
    if(!state?.enabled || !state.has_evidence || submitting.current)return
    if(newAttempt)pending.current=null
    pending.current??=crypto.randomUUID()
    const requestId=pending.current
    submitting.current=true;setBusy(true);setError('');setNotice('');setKnownFailure(false)
    const request=current.current
    try {
      const result=await api<{cached:boolean;analysis:Analysis}>(path,'POST',{request_id:requestId},65000)
      if(current.current!==request)return
      pending.current=null
      setState(previous => previous ? {...previous,latest:result.analysis}:previous)
      setNotice(result.cached ? 'Saved analysis reused. No new model call was made.' : 'AI analysis saved. Review its evidence and limitations before acting.')
      setRevision(value=>value+1)
    } catch(failure) {
      if(current.current!==request)return
      // A lost response does not mean generation failed. Recover this exact
      // receipt using read-only status checks, including its saved quota.
      if(!(failure instanceof ApiError) || failure.status>=500 || failure.status===409) {
        setNotice('Checking the saved request automatically… No additional model call is being made.')
        try {
          const outcome=await recoverAIRequest(
            ()=>api<State>(`${path}?request_id=${requestId}`),acceptSnapshot,()=>current.current===request,
          )
          if(current.current!==request)return
          if(outcome==='completed')return
          setNotice('')
          if(outcome==='failed')return
          setError('The connection was interrupted and automatic checks could not confirm completion. Check / retry the same request to keep its original ID; no new generation was started automatically.')
          return
        } catch(recoveryError) {
          if(current.current!==request)return
          setNotice('')
          setError(recoveryError instanceof Error ? recoveryError.message : 'Could not check the saved AI request.')
          return
        }
      }
      setError(failure instanceof Error ? failure.message : 'Could not complete AI analysis.')
      setKnownFailure(failure instanceof ApiError && [409,502].includes(failure.status))
    } finally {submitting.current=false;setBusy(false)}
  }

  const analysis=state?.latest, ids=new Set(eventIds)
  return <section className="panel incident-ai"><div className="panel-heading"><div><h2>AI incident analysis</h2><p>Evidence-grounded interpretation and suggested investigation. Analyst review required.</p></div></div>
    <div className="ai-content">
      {loading && <p role="status">Loading AI analysis status…</p>}
      {error && <p className="login-error" role="alert">{error}</p>}{notice && <p className="feedback" role="status">{notice}</p>}
      {!state && !loading && <button onClick={()=>setRevision(value=>value+1)}>Retry AI status</button>}
      {state && <>
        <p>{state.enabled ? `Provider: ${state.provider} · ${state.model}` : 'AI is not enabled. The project owner must finish provider setup. Existing detections and evidence remain available.'}</p>
        <p className="muted">Generating sends selected timestamps, event IDs/types, ports, protocol, stored priority and approved investigation references to OpenAI. Account names and IPs use aliases; raw logs, note text and sensor signature text are excluded. This does not make the context anonymous.</p>
        <p className="small muted">Generation attempts: {state.quota.daily_used}/{state.quota.daily_limit} today · {state.quota.monthly_used}/{state.quota.monthly_limit} this UTC month. Failed attempts count. Unchanged saved analyses are reused.</p>
        {!state.has_evidence && <p>No linked evidence is available for model interpretation.</p>}
        <div className="ai-actions"><button className="primary" disabled={busy || loading || (!knownFailure && (!state.enabled || !state.has_evidence))} onClick={()=>knownFailure ? setRevision(value=>value+1) : void analyze()}>{busy ? 'Analyzing evidence…' : knownFailure ? 'Check request status' : pending.current ? 'Check / retry same request' : 'Analyze incident'}</button>
          {knownFailure && <button disabled={busy || loading || !state.enabled} onClick={()=>void analyze(true)}>Start a new attempt (uses quota)</button>}
          <button disabled={busy || loading} onClick={()=>setRevision(value=>value+1)}>Refresh saved analysis</button></div>
      </>}
      {analysis && <div className="ai-result" aria-live="polite">
        <p className="small muted">AI generated · {analysis.model} · <time dateTime={analysis.generated_at} title={analysis.generated_at}>{new Date(analysis.generated_at).toLocaleString()}</time> · Knowledge {analysis.knowledge_version}</p>
        {analysis.outdated && <p role="status">Evidence or model configuration has changed since this analysis. Review the current timeline before requesting a fresh analysis.</p>}
        <h3>Summary</h3><p>{analysis.answer.summary}</p>
        <h3>AI observations</h3>{analysis.answer.observations.map((observation,index)=><article key={index}><p>{observation.text}</p><div className="ai-citations">{observation.event_ids.map(id=>ids.has(id)
          ? <a key={id} href={`#evidence-${id}`} title={id}>Evidence {id.slice(0,8)}</a> : <span key={id} title={id}>Evidence {id.slice(0,8)} (outside current timeline view)</span>)}</div></article>)}
        <h3>Interpretation</h3><p>{analysis.answer.interpretation}</p>
        <h3>Suggested investigation</h3><ol>{analysis.answer.investigation_steps.map((step,index)=><li key={index}><p>{step.text}</p><span className="small muted">References: {step.reference_ids.join(', ')}</span></li>)}</ol>
        <h3>References</h3><ul>{analysis.references.map(reference=><li key={reference.id}>{reference.url
          ? <a href={reference.url} target="_blank" rel="noopener noreferrer">{reference.title}</a> : reference.title}<span className="small muted"> · {reference.id}</span></li>)}</ul>
        <h3>Limitations</h3><ul>{[...analysis.answer.limitations,...analysis.context_limitations].map((limit,index)=><li key={index}>{limit}</li>)}</ul>
        {(analysis.omitted_linked_events>0 || analysis.omitted_related_events>0) && <p>Context excluded {analysis.omitted_linked_events} linked and {analysis.omitted_related_events} related event(s) to stay within limits.</p>}
        <p className="small muted">No containment, account changes or disposition changes were performed. AI interpretation does not establish compromise.</p>
      </div>}
    </div></section>
}
