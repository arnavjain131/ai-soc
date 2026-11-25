import React, { useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { Activity, ArrowRight, ChevronRight, Clock3, Database, Eye, FileSearch, LayoutDashboard, LockKeyhole, LogOut, Radio, RefreshCw, Shield, ShieldAlert, Terminal, X } from 'lucide-react'
import type { Session } from '@supabase/supabase-js'
import { api, ApiError, supabase } from './api'
import { AccountRecovery, SignInDialog } from './AccountAccess'
import { RECOVERY_PATH, recoveryCallback, recoveryExchange } from './accountRecovery'
import { NetworkEvents } from './NetworkEvents'
import { SecurityEvents } from './SecurityEvents'
import { WorkspaceAccess } from './WorkspaceAccess'
import { IncidentJournal } from './IncidentJournal'
import { IncidentQueue } from './IncidentQueue'
import { IncidentAssignment } from './IncidentAssignment'
import { initialQueueView, type QueueView } from './incidentFilters'
import { SourceHealth, SourceStatus } from './TelemetryHealth'
import { demoIncidents, demoSources, demoStats } from './demo'
import type { Detail, Incident, IncidentStatus, Source, Stats } from './types'
import { networkAddress } from './types'
import './styles.css'

function date(value: string) { return new Date(value).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZoneName: 'short' }) }
const statusLabel = (value: string) => value.replaceAll('_', ' ')
const IncidentAI = React.lazy(() => import('./IncidentAI').then(module => ({default:module.IncidentAI})))

function EvidenceTimeline({ detail }: { detail: Detail }) {
  const related = detail.related_network_events ?? []
  const relatedIds = new Set(related.map(event => event.id))
  const timeline = [...detail.events, ...related].sort(
    (a, b) => Date.parse(a.event_time) - Date.parse(b.event_time) || a.id.localeCompare(b.id),
  )

  return <section className="panel">
    <div className="panel-heading">
      <div>
        <h2>Evidence timeline</h2>
        {related.length > 0 && <p>Related network events match the TCP endpoints and occurred within two minutes of the failed-login window.</p>}
      </div>
      <span className="small muted">{detail.events.length} linked events{related.length > 0 && ` · ${related.length} related`}</span>
    </div>
    <div className="timeline">{timeline.map(event => <article key={event.id} id={`evidence-${event.id}`} tabIndex={-1}>
      <span className="timeline-point"/>
      <time dateTime={event.event_time} title={event.event_time}>{date(event.event_time)}</time>
      {'protocol' in event ? <>
        <h3>{relatedIds.has(event.id) ? 'Related ' : ''}{event.event_type === 'SURICATA_ALERT' ? 'Suricata alert' : 'Network flow'}</h3>
        {event.signature && <p><strong>{event.signature}</strong> · Signature {event.signature_id} · Suricata severity {event.severity}</p>}
        <p>{event.source_name} · {event.protocol} · {networkAddress(event.source_ip, event.source_port)} → {networkAddress(event.destination_ip, event.destination_port)}</p>
      </> : <>
        <h3>{statusLabel(event.event_type.toLowerCase())}</h3>
        <p><strong>{event.username}</strong> · {event.source_ip} → {networkAddress(event.destination_ip, event.destination_port)}</p>
      </>}
      <span className="mono muted">{event.id}</span>
    </article>)}</div>
  </section>
}

function App() {
  const [mode, setMode] = useState<'demo' | 'private'>('demo')
  const [session, setSession] = useState<Session | null>(null)
  const [loginOpen, setLoginOpen] = useState(false)
  const [access, setAccess] = useState<'loading' | 'allowed' | 'missing' | 'expired' | 'error'>('loading')
  const [error, setError] = useState(''), [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false), [loaded, setLoaded] = useState(false)
  const [stats, setStats] = useState<Stats>(demoStats), [sources, setSources] = useState<Source[]>(demoSources)
  const [detail, setDetail] = useState<Detail | null>(null)
  const [journalRefresh, setJournalRefresh] = useState(0)
  const [queueSaved,setQueueSaved]=useState<{boundary:string;view:QueueView}|null>(null)
  const [tab, setTab] = useState<'overview' | 'incidents' | 'sources' | 'network' | 'events' | 'members'>('overview')
  const [networkRefresh, setNetworkRefresh] = useState(0)
  const [eventsRefresh, setEventsRefresh] = useState(0)
  const [membersRefresh, setMembersRefresh] = useState(0)
  const [sourceNow, setSourceNow] = useState(Date.now)
  const [sourcesCheckedAt, setSourcesCheckedAt] = useState<number | null>(null)
  const [role, setRole] = useState(''), [sourceName, setSourceName] = useState(''), [sourceToken, setSourceToken] = useState('')
  const boundary = `${mode}:${session?.access_token || ''}`
  const boundaryRef = useRef(boundary)
  boundaryRef.current = boundary

  useEffect(() => {
    if (mode !== 'private' || !session) return
    setSourceNow(Date.now())
    const timer = window.setInterval(() => setSourceNow(Date.now()), 30000)
    return () => window.clearInterval(timer)
  }, [boundary])

  useEffect(() => {
    if (!supabase) return
    supabase.auth.getSession().then(({ data }) => setSession(data.session))
    const { data } = supabase.auth.onAuthStateChange((_event, next) => setSession(next))
    return () => data.subscription.unsubscribe()
  }, [])

  async function refresh() {
    const requestedBoundary = boundary
    setError(''); setBusy(true)
    try {
      if (mode === 'demo') { setStats(demoStats); setSources(demoSources) }
      else {
        const identity = await api<{ role: string }>('/api/me')
        if (boundaryRef.current !== requestedBoundary) return
        const [counts, sensors] = await Promise.all([api<Stats>('/api/dashboard/stats'), api<Source[]>('/api/sources')])
        if (boundaryRef.current !== requestedBoundary) return
        setStats(counts); setSources(sensors); setRole(identity.role)
        setAccess('allowed')
        setSourcesCheckedAt(Date.now()); setSourceNow(Date.now())
      }
      setQueueSaved(previous=>({boundary:requestedBoundary,view:previous?.boundary===requestedBoundary
        ? {...previous.view,request:{...previous.view.request,offset:0,asOf:undefined}} : initialQueueView}))
      setLoaded(true)
    } catch (e) {
      if (boundaryRef.current === requestedBoundary) {
        setError(e instanceof Error ? e.message : 'Could not load the workspace.')
        setAccess(e instanceof ApiError && e.status === 403 ? 'missing' : e instanceof ApiError && e.status === 401 ? 'expired' : 'error')
        if (e instanceof ApiError && (e.status === 401 || e.status === 403)) {
          setDetail(null); setSources([]); setSourceToken(''); setRole(''); setLoaded(false)
          setStats({ events: 0, alerts: 0, incidents: 0, sources: 0, open_incidents: 0 })
        }
      }
    }
    finally { if (boundaryRef.current === requestedBoundary) setBusy(false) }
  }

  useEffect(() => {
    setTab(current => mode === 'demo' && (current === 'network' || current === 'events' || current === 'members') ? 'overview' : current); setDetail(null); setNotice(''); setError(''); setLoaded(false); setBusy(false); setRole(''); setSourceToken(''); setSourceName('')
    setSourcesCheckedAt(null)
    setAccess('loading')
    // Clear data before switching boundaries so private failures never show demo metrics as real.
    setQueueSaved(null); setStats({ events: 0, alerts: 0, incidents: 0, sources: 0, open_incidents: 0 }); setSources([])
    if (mode === 'demo' || session) void refresh()
  }, [mode, session?.access_token])

  async function openIncident(item: Incident) {
    const requestedBoundary = boundary
    setError(''); setBusy(true)
    try {
      const next = mode === 'demo' ? demoIncidents.find(i => i.id === item.id)! : await api<Detail>(`/api/incidents/${item.id}`)
      if (boundaryRef.current === requestedBoundary) { setDetail(next); setJournalRefresh(value => value + 1) }
    }
    catch (e) { if (boundaryRef.current === requestedBoundary) setError(e instanceof Error ? e.message : 'Could not open incident.') }
    finally { if (boundaryRef.current === requestedBoundary) setBusy(false) }
  }

  async function changeStatus(value: IncidentStatus) {
    if (!detail) return
    const requestedBoundary = boundary
    if (mode === 'demo') { setNotice('The public demo is read-only. Analysts can update incidents in their private workspace.'); return }
    setBusy(true); setError('')
    try {
      await api(`/api/incidents/${detail.id}`, 'PATCH', { status: value })
      const updated = await api<Detail>(`/api/incidents/${detail.id}`)
      if (boundaryRef.current !== requestedBoundary) return
      setDetail(updated); setJournalRefresh(value => value + 1); await refresh()
      if (boundaryRef.current !== requestedBoundary) return
      setNotice('Disposition saved to the audit trail.')
    } catch (e) { if (boundaryRef.current === requestedBoundary) setError(e instanceof Error ? e.message : 'Could not update incident.') }
    finally { if (boundaryRef.current === requestedBoundary) setBusy(false) }
  }

  const queueView=queueSaved?.boundary===boundary ? queueSaved.view : initialQueueView
  const privateLocked = mode === 'private' && !session

  async function createSource(event: React.FormEvent) {
    event.preventDefault()
    const requestedBoundary = boundary
    setBusy(true); setError(''); setSourceToken('')
    try {
      const created = await api<{ token: string }>('/api/sources', 'POST', { name: sourceName.trim() })
      if (boundaryRef.current !== requestedBoundary) return
      setSourceToken(created.token); setSourceName(''); await refresh()
    } catch (e) { if (boundaryRef.current === requestedBoundary) setError(e instanceof Error ? e.message : 'Could not create source.') }
    finally { if (boundaryRef.current === requestedBoundary) setBusy(false) }
  }

  return <div className="shell">
    <aside className="sidebar">
      <a className="brand" href="#" aria-label="AI SOC home" onClick={e => { e.preventDefault(); setTab('overview'); setDetail(null) }}><span className="brand-icon"><Shield size={23}/></span><span>AI SOC<span className="brand-caption">SECURITY OPERATIONS</span></span></a>
      <div className="workspace-label">WORKSPACE <span>01</span></div>
      <nav aria-label="Main navigation">
        <button className={tab === 'overview' ? 'active' : ''} onClick={() => { setTab('overview'); setDetail(null) }}><LayoutDashboard size={18}/>Overview</button>
        <button className={tab === 'incidents' ? 'active' : ''} onClick={() => { setTab('incidents'); setDetail(null) }}><ShieldAlert size={18}/>Incidents <span className="nav-count">{stats.open_incidents}</span></button>
        <button className={tab === 'sources' ? 'active' : ''} onClick={() => { setTab('sources'); setDetail(null) }}><Radio size={18}/>Telemetry sources</button>
        {mode === 'private' && <button className={tab === 'events' ? 'active' : ''} onClick={() => { setTab('events'); setDetail(null) }}><Database size={18}/>Security events</button>}
        {mode === 'private' && <button className={tab === 'network' ? 'active' : ''} onClick={() => { setTab('network'); setDetail(null) }}><Activity size={18}/>Network events</button>}
        {mode === 'private' && role === 'admin' && <button className={tab === 'members' ? 'active' : ''} onClick={() => { setTab('members'); setDetail(null) }}><LockKeyhole size={18}/>Workspace access</button>}
      </nav>
      <div className="sidebar-note"><FileSearch size={19}/><strong>Evidence comes first.</strong><p>Trace every finding back to the events that support it.</p><span>EXPLAINABLE BY DESIGN</span></div>
      <div className="sidebar-bottom"><span className="dot"/>Foundation release <span>v0.1</span></div>
    </aside>

    <main>
      <header className="topbar"><div className="breadcrumb">Workspace <ChevronRight size={14}/><span>{mode === 'demo' ? 'Public demonstration' : 'Private analyst workspace'}</span></div>
        <div className="account-actions"><span className="mode-tag"><span className="dot"/>{mode === 'demo' ? 'DEMO' : 'PRIVATE'}</span>
          {mode === 'private' ? <button className="quiet" onClick={() => setMode('demo')}>View demo</button> : <button className="quiet" onClick={() => session ? setMode('private') : setLoginOpen(true)}><LockKeyhole size={14}/>Analyst sign in <ArrowRight size={14}/></button>}
          {session && <button className="icon-button" aria-label="Sign out" onClick={async () => { await supabase?.auth.signOut(); setMode('demo') }}><LogOut size={16}/></button>}
        </div>
      </header>
      <div className="content">
        <nav className="mobile-nav" aria-label="Mobile navigation">{(['overview', 'incidents', 'sources', 'events', 'network', 'members'] as const).filter(value => value === 'members' ? mode === 'private' && role === 'admin' : (value !== 'network' && value !== 'events') || mode === 'private').map(value => <button key={value} className={tab === value ? 'active' : ''} onClick={() => { setTab(value); setDetail(null) }}>{value === 'sources' ? 'Sources' : value === 'events' ? 'Security events' : value === 'members' ? 'Access' : value}</button>)}</nav>
        <div className="page-heading"><div><div className="eyebrow">YOUR SECURITY, IN CONTEXT</div><h1>{detail ? 'Incident investigation' : tab === 'members' ? 'Workspace access' : tab === 'network' ? 'Network events' : tab === 'events' ? 'Security events' : tab === 'sources' ? 'Telemetry sources' : tab === 'incidents' ? 'Incident queue' : 'Security overview'}</h1><p>Understand the signal. Follow the evidence. Make the call.</p></div><button className="secondary" disabled={busy || privateLocked} onClick={() => { if (detail) void openIncident(detail); else if (tab === 'members') { setMembersRefresh(value => value + 1); void refresh() } else if (tab === 'network') { setNetworkRefresh(value => value + 1); void refresh() } else if (tab === 'events') { setEventsRefresh(value => value + 1); void refresh() } else void refresh() }}><RefreshCw size={15} className={busy ? 'spin' : ''}/>Refresh</button></div>
        <div className="demo-banner"><Eye size={19}/><div><strong>{mode === 'demo' ? 'You’re exploring a demonstration workspace' : 'Private workspace · authenticated access'}</strong><p>{mode === 'demo' ? 'Synthetic authentication events. Fixed sample data, no live monitoring. All times use your browser’s timezone.' : 'Records below come from your backend. Only authorized members can access this workspace.'}</p></div><span>{mode === 'demo' ? 'READ ONLY' : 'RESTRICTED'}</span></div>
        {error && <div className="feedback error" role="alert">{error}<button onClick={() => setError('')} aria-label="Dismiss error"><X size={16}/></button></div>}
        {notice && <div className="feedback" role="status">{notice}<button onClick={() => setNotice('')} aria-label="Dismiss message"><X size={16}/></button></div>}
        {mode === 'private' && session && access === 'allowed' && loaded && !detail && <SourceHealth sources={sources} now={sourceNow} checkedAt={sourcesCheckedAt} onReview={() => setTab('sources')}/>}
        {privateLocked ? <section className="panel empty"><LockKeyhole size={30}/><h2>Sign in to your analyst workspace</h2><p>The public demo remains available without an account.</p><button className="primary" onClick={() => setLoginOpen(true)}>Analyst sign in <ArrowRight size={16}/></button></section>
          : mode === 'private' && access !== 'allowed' ? <section className="panel empty" aria-live="polite">
            <LockKeyhole size={30}/><h2>{access === 'missing' ? 'Workspace access required' : access === 'expired' ? 'Sign in again' : access === 'error' ? 'Workspace temporarily unavailable' : 'Checking workspace access…'}</h2>
            {access === 'missing' && <><p>Your account is signed in, but an administrator must grant access to an existing workspace. Password recovery does not change workspace membership.</p><p>Send your administrator this account ID:</p><code className="mono">{session?.user.id}</code></>}
            {access === 'expired' && <p>Your session could not be verified. Sign out and sign in again.</p>}
            {access === 'error' && <p>Your access could not be checked. Wait briefly and retry. No demo data is being shown as private telemetry.</p>}
            <div className="access-actions">{access !== 'loading' && <button className="primary" disabled={busy} onClick={() => void refresh()}>Check access again</button>}<button className="quiet" onClick={() => setMode('demo')}>View public demo</button></div>
          </section> : <>
          {detail ? <>
            <button className="back" onClick={() => setDetail(null)}>← Back to incident queue</button>
            <section className="panel incident-header"><div><div className="eyebrow">{detail.id.startsWith('demo') ? 'DEMONSTRATION INCIDENT' : 'INCIDENT'}</div><h2>{detail.title}</h2><span className="mono muted">{detail.id}</span></div><span className="severity">{detail.severity.toUpperCase()}</span></section>
            <div className="detail-grid"><EvidenceTimeline detail={detail}/>
              <div className="stack"><section className="panel risk"><div className="panel-heading"><h2>Risk breakdown</h2><ShieldAlert size={17}/></div><div className="risk-number">{detail.risk_score}<span>/100</span></div><p className="muted small">Prioritization score · not a probability</p>{Object.entries(detail.score_components).map(([key, value]) => <div className="score-line" key={key}><span>{statusLabel(key)}</span><strong>+{value}</strong></div>)}</section>
              <section className="panel"><div className="panel-heading"><h2>Detection rationale</h2></div>{detail.alerts.map(alert => <div className="rationale" key={alert.id}><code>{alert.rule_key}</code><p>{alert.explanation}</p></div>)}</section>
              <section className="panel disposition"><h2>Analyst disposition</h2><label htmlFor="disposition">Incident status</label><select id="disposition" value={detail.status} disabled={busy || ['closed', 'false_positive'].includes(detail.status)} onChange={e => void changeStatus(e.target.value as IncidentStatus)}>{['open', 'investigating', 'closed', 'false_positive'].map(s => <option key={s} value={s}>{statusLabel(s)}</option>)}</select></section></div>
            </div>
            {mode === 'private' && <IncidentAssignment key={`assignment:${boundary}:${detail.id}`} incidentId={detail.id} viewerId={session?.user.id} refreshKey={detail.updated_at} onChanged={()=>setJournalRefresh(value=>value+1)}/>}
            {mode === 'private' && <IncidentJournal key={`${boundary}:${detail.id}`} incidentId={detail.id} viewerId={session?.user.id} refreshKey={`${detail.updated_at}:${detail.status}:${journalRefresh}`}/>}
            {mode === 'private' && <React.Suspense fallback={<p role="status">Loading AI panel…</p>}><IncidentAI key={`${boundary}:${detail.id}`} incidentId={detail.id} eventIds={[...detail.events,...(detail.related_network_events ?? [])].map(event=>event.id)}/></React.Suspense>}
          </> : tab === 'members' && mode === 'private' && role === 'admin' ? <WorkspaceAccess key={boundary} refreshKey={membersRefresh}/> : tab === 'events' && mode === 'private' ? <SecurityEvents key={boundary} sessionKey={boundary} refreshKey={eventsRefresh} sources={sources}/> : tab === 'network' && mode === 'private' ? <NetworkEvents key={boundary} sessionKey={boundary} refreshKey={networkRefresh}/> : tab === 'sources' ? <section className="panel"><div className="panel-heading"><h2>Registered sources</h2><span className="muted small">{sources.length} sources</span></div>{mode === 'private' && role === 'admin' && <div className="source-create"><form onSubmit={createSource}><label htmlFor="source-name">Add a telemetry source</label><div><input id="source-name" placeholder="e.g. Authentication lab" required maxLength={100} value={sourceName} onChange={e => setSourceName(e.target.value)}/><button className="primary" disabled={busy || !sourceName.trim()}>Create source</button></div></form>{sourceToken && <div className="source-secret"><strong>Save this source token now</strong><p>It is displayed once. Keep it private and use it only in your collector or local smoke test.</p><textarea aria-label="New source token" readOnly value={sourceToken}/><button className="secondary" onClick={() => setSourceToken('')}>Hide token</button></div>}</div>}{sources.length ? sources.map(source => <div className="source-row" key={source.id}><span className="source-icon"><Terminal size={20}/></span><div className="source-identity"><strong>{source.name}</strong></div><SourceStatus source={source} now={sourceNow} demo={mode === 'demo'}/></div>) : <div className="empty"><Radio/><p>No sources yet. An administrator can create one in this view.</p></div>}</section> : <>
            <div className="metrics">{[
              { label: 'Open incidents', value: stats.open_incidents, icon: ShieldAlert, note: 'Awaiting analyst review', accent: 'orange' },
              { label: 'Detection alerts', value: stats.alerts, icon: Activity, note: 'Evidence-backed findings', accent: 'purple' },
              { label: 'Security events', value: stats.events, icon: Database, note: 'Persisted security records', accent: 'blue' },
              { label: 'Registered sources', value: stats.sources, icon: Radio, note: mode === 'demo' ? 'Synthetic fixture source' : 'Configured telemetry sources', accent: 'green' },
            ].map(metric => <section className={`metric ${metric.accent}`} key={metric.label}><div><span>{metric.label}</span><metric.icon size={18}/></div><strong>{loaded ? metric.value.toLocaleString() : '—'}</strong><p>{metric.note}</p></section>)}</div>
            <div className={tab==='incidents' ? 'overview-grid incident-list-layout' : 'overview-grid'}><IncidentQueue key={boundary} mode={mode} view={queueView} onViewChange={view=>{if(boundaryRef.current===boundary)setQueueSaved({boundary,view})}} onOpen={item=>void openIncident(item)} disabled={busy}/><div className="stack"><section className="panel pipeline"><div className="panel-heading"><h2>Detection pipeline</h2><Activity size={17}/></div><p className="muted small">Every finding has a traceable path.</p>{[{ label: 'Collect & normalize', note: 'Validated security events', icon: Database }, { label: 'Evaluate rules', note: 'Transparent detection logic', icon: Shield }, { label: 'Build incidents', note: 'Linked evidence & risk score', icon: FileSearch }].map((step, i) => <div className="pipeline-step" key={step.label}><span><step.icon size={17}/></span><div><strong>{step.label}</strong><p>{step.note}</p></div><small>0{i + 1}</small></div>)}</section><section className="ai-card"><div className="eyebrow">PRIVATE INCIDENT ANALYSIS</div><h2>Investigation, grounded<br/>in your evidence.</h2><p>Open a private incident for evidence-cited AI interpretation and investigation references. Provider activation is controlled by the project owner.</p><span><LockKeyhole size={13}/> AI availability is shown inside each private incident</span></section></div></div>
          </>}
        </>}
        <footer><span><Shield size={13}/>AI SOC Assistant</span><span>Collect. Detect. Investigate.</span><span>Foundation · November 2026</span></footer>
      </div>
    </main>
    {loginOpen && <SignInDialog onClose={() => setLoginOpen(false)} onSignedIn={() => { setLoginOpen(false); setMode('private') }}/>}
  </div>
}

// Recovery never mounts the private application or trusts a pre-existing session.
const isRecovery = window.location.pathname === RECOVERY_PATH
const callback = isRecovery ? recoveryCallback(window.location.href) : { code: null, error: false }
if (isRecovery) window.history.replaceState(null, '', RECOVERY_PATH)
const exchange = supabase ? recoveryExchange(code => supabase!.auth.exchangeCodeForSession(code), callback) : async () => false
createRoot(document.getElementById('root')!).render(<React.StrictMode>{isRecovery ? <AccountRecovery exchange={exchange}/> : <App/>}</React.StrictMode>)
