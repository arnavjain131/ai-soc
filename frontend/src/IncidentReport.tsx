import {useEffect,useRef,useState} from 'react'
import {apiReport} from './api'
import {reportRequest,type ReportFormat} from './reportDownload'
import './incidentReport.css'

export function IncidentReport({incidentId}:{incidentId:string}) {
  const [format,setFormat]=useState<ReportFormat>('html'),[includeAI,setIncludeAI]=useState(true)
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('')
  const request=useRef<AbortController|null>(null)
  useEffect(()=>()=>{request.current?.abort();request.current=null},[incidentId])
  async function download() {
    if(request.current)return
    const controller=new AbortController();request.current=controller
    setBusy(true);setError('');setNotice('')
    try {
      const spec=reportRequest(incidentId,format,includeAI)
      const blob=await apiReport(spec.path,format,controller.signal)
      if(request.current!==controller || controller.signal.aborted)return
      const url=URL.createObjectURL(blob)
      try {
        const anchor=document.createElement('a');anchor.href=url;anchor.download=spec.filename
        document.body.appendChild(anchor)
        try {anchor.click()}finally {anchor.remove()}
      } finally {window.setTimeout(()=>URL.revokeObjectURL(url),1000)}
      setNotice('Report download started. Check your browser’s downloads. No new AI analysis was generated.')
    } catch(failure) {
      if(request.current===controller && !controller.signal.aborted)setError(failure instanceof Error?failure.message:'Could not download report.')
    } finally {if(request.current===controller){request.current=null;setBusy(false)}}
  }
  return <section className="panel incident-report"><div className="panel-heading"><div><h2>Investigation report</h2><p>Download a private snapshot of incident evidence, related network context, ownership, notes and history.</p></div></div>
    <div className="report-body"><label>Report format<select disabled={busy} value={format} onChange={event=>setFormat(event.target.value as ReportFormat)}><option value="html">Printable HTML (.html)</option><option value="json">Structured JSON (.json)</option></select></label>
      <label className="report-checkbox"><input type="checkbox" checked={includeAI} disabled={busy} onChange={event=>setIncludeAI(event.target.checked)}/>Include the latest saved AI analysis, if available</label>
      <p className="small muted">Includes private usernames, network addresses and analyst notes. Excludes collector credentials and arbitrary raw event payloads. HTML reports open offline; use Print → Save as PDF if needed.</p>
      <button className="primary" disabled={busy} onClick={()=>void download()}>{busy?'Preparing report…':'Download report'}</button>
      {error && <p role="alert" className="login-error">{error}</p>}{notice && <p role="status">{notice}</p>}
    </div></section>
}
