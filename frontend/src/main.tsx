import React, { useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { Activity, ArrowDownRight, ArrowRight, Check, ChevronRight, Clock3, Database, Eye, FileSearch, LayoutDashboard, LockKeyhole, LogOut, Radio, RefreshCw, Search, Shield, ShieldAlert, Terminal, X } from 'lucide-react'
import type { Session } from '@supabase/supabase-js'
import { api, supabase } from './api'
import { NetworkEvents } from './NetworkEvents'
import { demoIncidents, demoSources, demoStats } from './demo'
import type { Detail, Incident, IncidentStatus, Source, Stats } from './types'
import { networkAddress } from './types'
import './styles.css'

function date(value: string) { return new Date(value).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZoneName: 'short' }) }
const statusLabel = (value: string) => value.replaceAll('_', ' ')

function EvidenceTimeline({ detail }: { detail: Detail }) {
  const related = detail.related_network_events ?? []
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
    <div className="timeline">{timeline.map(event => <article key={event.id}>
      <span className="timeline-point"/>
      <time dateTime={event.event_time} title={event.event_time}>{date(event.event_time)}</time>
      {'protocol' in event ? <>
        <h3>{event.event_type === 'SURICATA_ALERT' ? 'Related Suricata alert' : 'Related network flow'}</h3>
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
  const [email, setEmail] = useState(''), [password, setPassword] = useState('')
  const [error, setError] = useState(''), [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false), [loaded, setLoaded] = useState(false)
  const [incidents, setIncidents] = useState<Incident[]>(demoIncidents)
  const [stats, setStats] = useState<Stats>(demoStats), [sources, setSources] = useState<Source[]>(demoSources)
  const [detail, setDetail] = useState<Detail | null>(null)
  const [search, setSearch] = useState(''), [status, setStatus] = useState('all')
  const [tab, setTab] = useState<'overview' | 'incidents' | 'sources' | 'network'>('overview')
  const [networkRefresh, setNetworkRefresh] = useState(0)
  const [role, setRole] = useState(''), [sourceName, setSourceName] = useState(''), [sourceToken, setSourceToken] = useState('')
  const boundary = `${mode}:${session?.access_token || ''}`
  const boundaryRef = useRef(boundary)
  boundaryRef.current = boundary

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
      if (mode === 'demo') { setIncidents(demoIncidents); setStats(demoStats); setSources(demoSources) }
      else {
        const [items, counts, sensors, identity] = await Promise.all([api<Incident[]>('/api/incidents?limit=100'), api<Stats>('/api/dashboard/stats'), api<Source[]>('/api/sources'), api<{ role: string }>('/api/me')])
        if (boundaryRef.current !== requestedBoundary) return
        setIncidents(items); setStats(counts); setSources(sensors); setRole(identity.role)
      }
      setLoaded(true)
    } catch (e) { if (boundaryRef.current === requestedBoundary) setError(e instanceof Error ? e.message : 'Could not load the workspace.') }
    finally { if (boundaryRef.current === requestedBoundary) setBusy(false) }
  }

  useEffect(() => {
    setTab(current => mode === 'demo' && current === 'network' ? 'overview' : current); setDetail(null); setNotice(''); setError(''); setLoaded(false); setBusy(false); setRole(''); setSourceToken(''); setSourceName('')
    // Clear data before switching boundaries so private failures never show demo metrics as real.
    setIncidents([]); setStats({ events: 0, alerts: 0, incidents: 0, sources: 0, open_incidents: 0 }); setSources([])
    if (mode === 'demo' || session) void refresh()
  }, [mode, session?.access_token])

  async function signIn(event: React.FormEvent) {
    event.preventDefault(); setError(''); setBusy(true)
    try {
      if (!supabase) throw new Error('Private login is not connected yet. Configure the Supabase project URL and publishable key first.')
      const { error: authError } = await supabase.auth.signInWithPassword({ email, password })
      if (authError) throw authError
      setPassword(''); setLoginOpen(false); setMode('private')
    } catch (e) { setError(e instanceof Error ? e.message : 'Sign in failed.') }
    finally { setBusy(false) }
  }

  async function openIncident(item: Incident) {
    const requestedBoundary = boundary
    setError(''); setBusy(true)
    try {
      const next = mode === 'demo' ? demoIncidents.find(i => i.id === item.id)! : await api<Detail>(`/api/incidents/${item.id}`)
      if (boundaryRef.current === requestedBoundary) setDetail(next)
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
      setDetail(updated); await refresh()
      if (boundaryRef.current !== requestedBoundary) return
      setNotice('Disposition saved to the audit trail.')
    } catch (e) { if (boundaryRef.current === requestedBoundary) setError(e instanceof Error ? e.message : 'Could not update incident.') }
    finally { if (boundaryRef.current === requestedBoundary) setBusy(false) }
  }

  const filtered = incidents.filter(i => (status === 'all' || i.status === status) && `${i.title} ${i.id}`.toLowerCase().includes(search.toLowerCase()))
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
        {mode === 'private' && <button className={tab === 'network' ? 'active' : ''} onClick={() => { setTab('network'); setDetail(null) }}><Activity size={18}/>Network events</button>}
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
        <nav className="mobile-nav" aria-label="Mobile navigation">{(['overview', 'incidents', 'sources', 'network'] as const).filter(value => value !== 'network' || mode === 'private').map(value => <button key={value} className={tab === value ? 'active' : ''} onClick={() => { setTab(value); setDetail(null) }}>{value === 'sources' ? 'Sources' : value}</button>)}</nav>
        <div className="page-heading"><div><div className="eyebrow">YOUR SECURITY, IN CONTEXT</div><h1>{detail ? 'Incident investigation' : tab === 'network' ? 'Network events' : tab === 'sources' ? 'Telemetry sources' : tab === 'incidents' ? 'Incident queue' : 'Security overview'}</h1><p>Understand the signal. Follow the evidence. Make the call.</p></div><button className="secondary" disabled={busy || privateLocked} onClick={() => { if (detail) void openIncident(detail); else if (tab === 'network') setNetworkRefresh(value => value + 1); else void refresh() }}><RefreshCw size={15} className={busy ? 'spin' : ''}/>Refresh</button></div>
        <div className="demo-banner"><Eye size={19}/><div><strong>{mode === 'demo' ? 'You’re exploring a demonstration workspace' : 'Private workspace · authenticated access'}</strong><p>{mode === 'demo' ? 'Synthetic authentication events. Fixed sample data, no live monitoring. All times use your browser’s timezone.' : 'Records below come from your backend. Only authorized members can access this workspace.'}</p></div><span>{mode === 'demo' ? 'READ ONLY' : 'RESTRICTED'}</span></div>
        {error && <div className="feedback error" role="alert">{error}<button onClick={() => setError('')} aria-label="Dismiss error"><X size={16}/></button></div>}
        {notice && <div className="feedback" role="status">{notice}<button onClick={() => setNotice('')} aria-label="Dismiss message"><X size={16}/></button></div>}
        {privateLocked ? <section className="panel empty"><LockKeyhole size={30}/><h2>Sign in to your analyst workspace</h2><p>The public demo remains available without an account.</p><button className="primary" onClick={() => setLoginOpen(true)}>Analyst sign in <ArrowRight size={16}/></button></section> : <>
          {detail ? <>
            <button className="back" onClick={() => setDetail(null)}>← Back to incident queue</button>
            <section className="panel incident-header"><div><div className="eyebrow">{detail.id.startsWith('demo') ? 'DEMONSTRATION INCIDENT' : 'INCIDENT'}</div><h2>{detail.title}</h2><span className="mono muted">{detail.id}</span></div><span className="severity">{detail.severity.toUpperCase()}</span></section>
            <div className="detail-grid"><EvidenceTimeline detail={detail}/>
              <div className="stack"><section className="panel risk"><div className="panel-heading"><h2>Risk breakdown</h2><ShieldAlert size={17}/></div><div className="risk-number">{detail.risk_score}<span>/100</span></div><p className="muted small">Prioritization score · not a probability</p>{Object.entries(detail.score_components).map(([key, value]) => <div className="score-line" key={key}><span>{statusLabel(key)}</span><strong>+{value}</strong></div>)}</section>
              <section className="panel"><div className="panel-heading"><h2>Detection rationale</h2></div>{detail.alerts.map(alert => <div className="rationale" key={alert.id}><code>{alert.rule_key}</code><p>{alert.explanation}</p></div>)}</section>
              <section className="panel disposition"><h2>Analyst disposition</h2><label htmlFor="disposition">Incident status</label><select id="disposition" value={detail.status} disabled={busy || ['closed', 'false_positive'].includes(detail.status)} onChange={e => void changeStatus(e.target.value as IncidentStatus)}>{['open', 'investigating', 'closed', 'false_positive'].map(s => <option key={s} value={s}>{statusLabel(s)}</option>)}</select></section></div>
            </div>
          </> : tab === 'network' && mode === 'private' ? <NetworkEvents key={boundary} sessionKey={boundary} refreshKey={networkRefresh}/> : tab === 'sources' ? <section className="panel"><div className="panel-heading"><h2>Registered sources</h2><span className="muted small">{sources.length} sources</span></div>{mode === 'private' && role === 'admin' && <div className="source-create"><form onSubmit={createSource}><label htmlFor="source-name">Add a telemetry source</label><div><input id="source-name" placeholder="e.g. Authentication lab" required maxLength={100} value={sourceName} onChange={e => setSourceName(e.target.value)}/><button className="primary" disabled={busy || !sourceName.trim()}>Create source</button></div></form>{sourceToken && <div className="source-secret"><strong>Save this source token now</strong><p>It is displayed once. Keep it private and use it only in your collector or local smoke test.</p><textarea aria-label="New source token" readOnly value={sourceToken}/><button className="secondary" onClick={() => setSourceToken('')}>Hide token</button></div>}</div>}{sources.length ? sources.map(source => <div className="source-row" key={source.id}><span className="source-icon"><Terminal size={20}/></span><div><strong>{source.name}</strong><p>{source.last_seen ? `Last received ${date(source.last_seen)}` : 'No events received yet'}</p></div><span className="status">{source.enabled ? 'enabled' : 'revoked'}</span></div>) : <div className="empty"><Radio/><p>No sources yet. An administrator can create one in this view.</p></div>}</section> : <>
            <div className="metrics">{[
              { label: 'Open incidents', value: stats.open_incidents, icon: ShieldAlert, note: 'Awaiting analyst review', accent: 'orange' },
              { label: 'Detection alerts', value: stats.alerts, icon: Activity, note: 'Evidence-backed findings', accent: 'purple' },
              { label: 'Security events', value: stats.events, icon: Database, note: 'Persisted security records', accent: 'blue' },
              { label: 'Registered sources', value: stats.sources, icon: Radio, note: mode === 'demo' ? 'Synthetic fixture source' : 'Configured telemetry sources', accent: 'green' },
            ].map(metric => <section className={`metric ${metric.accent}`} key={metric.label}><div><span>{metric.label}</span><metric.icon size={18}/></div><strong>{loaded ? metric.value.toLocaleString() : '—'}</strong><p>{metric.note}</p></section>)}</div>
            <div className="overview-grid"><section className="panel queue"><div className="panel-heading"><div><h2>Incident queue <span className="count">{incidents.length}</span></h2><p>Prioritized findings that need a closer look.</p></div><span className="small muted">LATEST 100</span></div>
              <div className="filters"><label className="search"><Search size={16}/><input aria-label="Search incidents" placeholder="Search incidents…" value={search} onChange={e => setSearch(e.target.value)}/></label><select aria-label="Filter by status" value={status} onChange={e => setStatus(e.target.value)}><option value="all">All statuses</option>{['open', 'investigating', 'closed', 'false_positive'].map(s => <option key={s} value={s}>{statusLabel(s)}</option>)}</select></div>
              <div className="table-wrap"><table><thead><tr><th>INCIDENT</th><th>SEVERITY</th><th>STATUS</th><th>RISK</th><th><span className="sr-only">Open</span></th></tr></thead><tbody>{filtered.map(item => <tr key={item.id}><td><button className="incident-link" onClick={() => void openIncident(item)}><span className="incident-symbol"><ShieldAlert size={18}/></span><span>{item.title}<small>{date(item.created_at)}</small></span></button></td><td><span className="severity">{item.severity}</span></td><td><span className={`status ${item.status}`}><span/>{statusLabel(item.status)}</span></td><td><strong className="risk-cell">{item.risk_score}</strong><span className="muted"> /100</span></td><td><button className="icon-button" disabled={busy} aria-label={`Investigate ${item.title}`} onClick={() => void openIncident(item)}><ArrowDownRight size={18}/></button></td></tr>)}</tbody></table></div>
              {!filtered.length && <div className="empty"><FileSearch size={26}/><p>{busy ? 'Loading incidents…' : error ? 'Workspace data could not be loaded. Check the error above and refresh.' : 'No incidents match this view.'}</p></div>}
              <div className="table-footer"><span>{filtered.length} of {incidents.length} loaded incidents</span><span>Rule-based detection <Check size={13}/></span></div>
            </section><div className="stack"><section className="panel pipeline"><div className="panel-heading"><h2>Detection pipeline</h2><Activity size={17}/></div><p className="muted small">Every finding has a traceable path.</p>{[{ label: 'Collect & normalize', note: 'Validated security events', icon: Database }, { label: 'Evaluate rules', note: 'Transparent detection logic', icon: Shield }, { label: 'Build incidents', note: 'Linked evidence & risk score', icon: FileSearch }].map((step, i) => <div className="pipeline-step" key={step.label}><span><step.icon size={17}/></span><div><strong>{step.label}</strong><p>{step.note}</p></div><small>0{i + 1}</small></div>)}</section><section className="ai-card"><div className="eyebrow">COMING IN A LATER MILESTONE</div><h2>Investigation, grounded<br/>in your evidence.</h2><p>The AI assistant will connect incident facts with response procedures and cite its sources.</p><span><LockKeyhole size={13}/> AI is not connected in this release</span></section></div></div>
          </>}
        </>}
        <footer><span><Shield size={13}/>AI SOC Assistant</span><span>Collect. Detect. Investigate.</span><span>Foundation · November 2026</span></footer>
      </div>
    </main>
    {loginOpen && <div className="modal-backdrop" onClick={e => { if (e.target === e.currentTarget) setLoginOpen(false) }}><section className="login panel" role="dialog" aria-modal="true" aria-labelledby="login-title" onKeyDown={e => { if (e.key === 'Escape') setLoginOpen(false) }}><button className="modal-close icon-button" aria-label="Close sign in" onClick={() => setLoginOpen(false)}><X size={20}/></button><span className="brand-icon"><LockKeyhole size={24}/></span><h2 id="login-title">Your analyst workspace</h2><p className="muted">Sign in with an account invited by your administrator.</p>{!supabase && <div className="feedback">Cloud login needs your Supabase project configuration. The public demo is ready to explore.</div>}<form onSubmit={signIn}><label htmlFor="email">Email address</label><input id="email" type="email" autoComplete="username" required autoFocus value={email} onChange={e => setEmail(e.target.value)}/><label htmlFor="password">Password</label><input id="password" type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)}/>{error && <p role="alert" className="login-error">{error}</p>}<button className="primary" disabled={busy || !supabase}>{busy ? 'Signing in…' : 'Sign in'}<ArrowRight size={16}/></button></form><p className="small muted">No public registration. Ask your administrator for access.</p></section></div>}
  </div>
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>)
