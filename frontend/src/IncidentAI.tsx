import { useEffect, useRef, useState } from 'react'
import { api, ApiError } from './api'
import { aiFailureMessage, mergeAIResult, recoverAIRequest, type AIRequestReceipt } from './aiRequestRecovery'
import './incidentAI.css'

type HistoricalCase={id:string;title?:string;created_at:string;status:string;severity:string;risk_score:number|null;shared_rules:string[]}
type Analysis = {
  id:string; generated_at:string; model:string; outdated:boolean; knowledge_version:string
  question?:string|null
  answer:{ summary:string; observations:{text:string;event_ids:string[]}[]; interpretation:string;
    investigation_steps:{text:string;reference_ids:string[]}[]; limitations:string[];
    historical_observations?:{text:string;case_ids:string[]}[] }
  historical_cases?:HistoricalCase[]
  references:{id:string;title:string;url:string|null;guidance?:string;document_id?:string;section?:string;version?:string;content_hash?:string}[]; context_limitations:string[]
  omitted_linked_events:number; omitted_related_events:number
}
type State = {enabled:boolean;has_evidence:boolean;provider:string;model:string;
  quota:{daily_used:number;daily_limit:number;monthly_used:number;monthly_limit:number};latest:Analysis|null;
  questions?:Analysis[];
  knowledge?:{version:string;method:string;document_count:number;section_count:number};
  similar_incidents?:HistoricalCase[];
  history_retrieval?:{method:string;lookback_days:number;display_limit:number;ai_limit:number};
  request?:AIRequestReceipt<Analysis>|null}

export function IncidentAI({ incidentId, eventIds, onOpenIncident, navigationBusy=false }: { incidentId:string; eventIds:string[];onOpenIncident?:(id:string)=>void;navigationBusy?:boolean }) {
  const [state,setState]=useState<State|null>(null), [loading,setLoading]=useState(true), [busy,setBusy]=useState(false)
  const [error,setError]=useState(''), [notice,setNotice]=useState(''), [knownFailure,setKnownFailure]=useState(false)
  const [revision,setRevision]=useState(0)
  const [question,setQuestion]=useState(''), [selectedQuestion,setSelectedQuestion]=useState<Analysis|null>(null)
  const [revealRequest,setRevealRequest]=useState(0)
  const resultPanel=useRef<HTMLDivElement|null>(null)
  const pendingQuestion=useRef<string|null>(null)
  const pending=useRef<string|null>(null), submitting=useRef(false), current=useRef(0)
  const path=`/api/incidents/${incidentId}/ai-analysis`
  function openAnalysis(answer:Analysis|null) {
    setSelectedQuestion(answer)
    setRevealRequest(value=>value+1)
  }
  useEffect(()=>{
    if(!revealRequest)return
    resultPanel.current?.focus({preventScroll:true})
    resultPanel.current?.scrollIntoView({block:'start',behavior:'instant'})
  },[revealRequest])
  function acceptSnapshot(result:State) {
    if(pending.current && result.request?.state==='completed' && result.request.analysis) {
      pending.current=null
      setError('');setKnownFailure(false)
      setNotice('Saved AI analysis recovered automatically. No additional model call was made.')
      if(result.request.analysis.question) {
        openAnalysis(result.request.analysis)
      } else openAnalysis(null)
      setState(mergeAIResult(result,result.request.analysis))
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
    pending.current=null;pendingQuestion.current=null
    setQuestion('');setSelectedQuestion(null);setKnownFailure(false)
  },[incidentId])
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

  async function analyze(newAttempt=false, requestedQuestion:string|null=null) {
    if(!state?.enabled || !state.has_evidence || submitting.current)return
    if(newAttempt)pending.current=null
    if(!pending.current)pendingQuestion.current=requestedQuestion
    pending.current??=crypto.randomUUID()
    const requestId=pending.current
    submitting.current=true;setBusy(true);setError('');setNotice('');setKnownFailure(false)
    const request=current.current
    try {
      const result=await api<{cached:boolean;analysis:Analysis}>(path,'POST',{
        request_id:requestId,...(pendingQuestion.current ? {question:pendingQuestion.current} : {}),
      },65000)
      if(current.current!==request)return
      pending.current=null
      openAnalysis(result.analysis.question ? result.analysis : null)
      setState(previous => previous ? mergeAIResult(previous,result.analysis):previous)
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
      if(failure instanceof ApiError && [400,403,404,413,422,429,503].includes(failure.status))pending.current=null
    } finally {submitting.current=false;setBusy(false)}
  }

  const analysis=selectedQuestion ? state?.questions?.find(item=>item.id===selectedQuestion.id) ?? selectedQuestion : state?.latest, ids=new Set(eventIds)
  return <section className="panel incident-ai"><div className="panel-heading"><div><h2>AI incident analysis</h2><p>Evidence-grounded interpretation and suggested investigation. Analyst review required.</p></div></div>
    <div className="ai-content">
      {loading && <p role="status">Loading AI analysis status…</p>}
      {error && <p className="login-error" role="alert">{error}</p>}{notice && <p className="feedback" role="status">{notice}</p>}
      {!state && !loading && <button onClick={()=>setRevision(value=>value+1)}>Retry AI status</button>}
      {state && <>
        <p>{state.enabled ? `Provider: ${state.provider} · ${state.model}` : 'AI is not enabled. The project owner must finish provider setup. Existing detections and evidence remain available.'}</p>
        <p className="muted">Generating sends selected timestamps, event IDs/types, ports, protocol, stored priority and approved investigation references to OpenAI. Account names and IPs use aliases; raw logs, note text and sensor signature text are excluded. This does not make the context anonymous.</p>
        <p className="small muted">Generation attempts: {state.quota.daily_used}/{state.quota.daily_limit} today · {state.quota.monthly_used}/{state.quota.monthly_limit} this UTC month. Failed attempts count. Unchanged saved analyses are reused.</p>
        {state.knowledge && <p className="small muted">Approved knowledge: {state.knowledge.document_count} procedures · {state.knowledge.section_count} sections. Relevant guidance is selected locally using keywords and the incident detection type. No live web search.</p>}
        {state.history_retrieval && <div className="ai-history-cases"><h3>Earlier incidents with matching detections</h3><p className="small muted">Up to {state.history_retrieval.display_limit} earlier-created incidents in this workspace, within {state.history_retrieval.lookback_days} days before this incident was created. Ranked by shared detection rules, then creation time. A match does not establish a shared attacker, host or cause. Opening a case uses no AI credit.</p>
          {!state.similar_incidents?.length ? <p>No earlier incidents matched these detection rules within this window.</p> : <ul>{state.similar_incidents.map(item=><li key={item.id}><strong>{item.title}</strong><p className="small muted">Created {new Date(item.created_at).toLocaleString()} · {item.status.replaceAll('_',' ')} · {item.severity} · risk {item.risk_score}/100</p><p className="small muted">Shared rules: {item.shared_rules.join(', ')}</p><p className="small muted">Incident {item.id}</p>{onOpenIncident && <button type="button" disabled={navigationBusy} onClick={()=>onOpenIncident(item.id)}>Open earlier incident {item.id.slice(0,8)}</button>}</li>)}</ul>}
          <p className="small muted">New AI requests include at most {state.history_retrieval.ai_limit} matched case summaries: incident IDs, creation times, status, priority and shared rules. Historical titles, account names, addresses, notes and logs are excluded. Saved answers keep the metadata used when generated.</p></div>}
        {!state.has_evidence && <p>No linked evidence is available for model interpretation.</p>}
        <div className="ai-actions"><button className="primary" disabled={busy || loading || (!knownFailure && (!state.enabled || !state.has_evidence))} onClick={()=>knownFailure ? setRevision(value=>value+1) : void analyze()}>{busy ? 'Analyzing evidence…' : knownFailure ? 'Check request status' : pending.current ? 'Check / retry same request' : 'Analyze incident'}</button>
          {knownFailure && <button disabled={busy || loading || !state.enabled} onClick={()=>void analyze(true,pendingQuestion.current)}>Start a new attempt (uses quota)</button>}
          <button disabled={busy || loading} onClick={()=>setRevision(value=>value+1)}>Refresh saved analysis</button></div>
        <form className="ai-question-form" onSubmit={event=>{event.preventDefault();void analyze(false,question.trim())}}>
          <h3>Ask about this incident</h3>
          <p className="small muted">Each question uses the same workspace AI quota. Answers use current incident evidence and approved references. Previous answers are not sent as conversation context.</p>
          <div className="ai-actions">{['Why was this incident flagged?', 'Does the evidence show a successful login?', 'What should I investigate next?', 'Are there similar earlier incidents?'].map(text=><button type="button" key={text} disabled={busy || !!pending.current} onClick={()=>setQuestion(text)}>{text}</button>)}</div>
          <label htmlFor={`ai-question-${incidentId}`}>Investigation question</label>
          <textarea id={`ai-question-${incidentId}`} value={question} minLength={3} maxLength={500} rows={3} required disabled={busy || !!pending.current} onChange={event=>setQuestion(event.target.value)} aria-describedby={`ai-question-privacy-${incidentId}`} />
          <p className="small muted" id={`ai-question-privacy-${incidentId}`}>Your question is sent to OpenAI and saved for workspace members. Known account names and IPs from selected evidence are replaced with aliases; other text may remain identifiable. Use host/account aliases and never include passwords, tokens or other secrets.</p>
          <button className="primary" type="submit" disabled={busy || loading || !!pending.current || !state.enabled || !state.has_evidence || question.trim().length<3}>Ask question (uses quota)</button>
        </form>
        {!!state.questions?.length && <div className="ai-question-history"><h3>Saved questions</h3><p className="small muted">Select a question to view its saved answer below. No model call is made.</p><ul>{state.questions.map(item=><li key={item.id}><button type="button" aria-pressed={selectedQuestion?.id===item.id} aria-controls={`ai-answer-${incidentId}`} onClick={()=>openAnalysis(item)}><span>{item.question}</span><span className="small">{selectedQuestion?.id===item.id ? 'Viewing answer' : 'Open saved answer →'}</span></button> <time className="small muted" dateTime={item.generated_at}>{new Date(item.generated_at).toLocaleString()}</time></li>)}</ul></div>}
        {selectedQuestion && <button className="ai-summary-button" type="button" onClick={()=>openAnalysis(null)}>Show incident summary</button>}
      </>}
      {analysis && <div ref={resultPanel} id={`ai-answer-${incidentId}`} className="ai-result" role="region" aria-labelledby={`ai-answer-title-${incidentId}`} tabIndex={-1}>
        <h3 id={`ai-answer-title-${incidentId}`} className="ai-answer-title">{analysis.question ? `Answer: ${analysis.question}` : 'Incident summary'}</h3>
        <p className="small muted">AI generated · {analysis.model} · <time dateTime={analysis.generated_at} title={analysis.generated_at}>{new Date(analysis.generated_at).toLocaleString()}</time> · Knowledge {analysis.knowledge_version}</p>
        {analysis.outdated && <p role="status">Evidence, knowledge or model configuration has changed since this analysis. The saved answer remains available; review current evidence before explicitly requesting a fresh analysis.</p>}
        <h3>{analysis.question ? 'Answer' : 'Summary'}</h3><p>{analysis.answer.summary}</p>
        <h3>AI observations</h3>{analysis.answer.observations.map((observation,index)=><article key={index}><p>{observation.text}</p><div className="ai-citations">{observation.event_ids.map(id=>ids.has(id)
          ? <a key={id} href={`#evidence-${id}`} title={id}>Evidence {id.slice(0,8)}</a> : <span key={id} title={id}>Evidence {id.slice(0,8)} (outside current timeline view)</span>)}</div></article>)}
        <h3>Interpretation</h3><p>{analysis.answer.interpretation}</p>
        {!!analysis.answer.historical_observations?.length && <><h3>Earlier case comparison</h3><p className="small muted">Based on saved case metadata, not earlier case logs or confirmed investigation outcomes.</p>{analysis.answer.historical_observations.map((item,index)=><article key={index}><p>{item.text}</p><div className="ai-citations">{item.case_ids.map(id=>{
          const historical=analysis.historical_cases?.find(candidate=>candidate.id===id)
          return historical ? <span key={id}>{onOpenIncident ? <button type="button" disabled={navigationBusy} onClick={()=>onOpenIncident(id)}>Open cited case {id.slice(0,8)}</button> : `Case ${id}`}<span className="small muted"> · saved status {historical.status.replaceAll('_',' ')} · created {new Date(historical.created_at).toLocaleString()}</span></span> : <span key={id}>Case {id.slice(0,8)} (not in saved context)</span>
        })}</div></article>)}</>}
        <h3>Suggested investigation</h3><ol>{analysis.answer.investigation_steps.map((step,index)=><li key={index}><p>{step.text}</p><span className="small muted">References: {step.reference_ids.join(', ')}</span></li>)}</ol>
        <h3>References</h3><ul>{analysis.references.map(reference=><li key={reference.id}>{reference.document_id ? <>{reference.title}{reference.url && <> · <a href={reference.url} target="_blank" rel="noopener noreferrer">Supporting source</a></>}</> : reference.url
          ? <a href={reference.url} target="_blank" rel="noopener noreferrer">{reference.title}</a> : reference.title}<span className="small muted"> · {reference.id}</span>{reference.document_id && <details className="ai-guidance"><summary>Read retrieved guidance</summary><p>{reference.guidance}</p><p className="small muted">Document {reference.document_id} · version {reference.version} · section {reference.section}</p><p className="small muted">Content fingerprint: {reference.content_hash}</p></details>}</li>)}</ul>
        <h3>Limitations</h3><ul>{[...analysis.answer.limitations,...analysis.context_limitations].map((limit,index)=><li key={index}>{limit}</li>)}</ul>
        {(analysis.omitted_linked_events>0 || analysis.omitted_related_events>0) && <p>Context excluded {analysis.omitted_linked_events} linked and {analysis.omitted_related_events} related event(s) to stay within limits.</p>}
        <p className="small muted">No containment, account changes or disposition changes were performed. AI interpretation does not establish compromise.</p>
      </div>}
    </div></section>
}
