import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { api } from './api'
import type { Source } from './types'
import { networkAddress } from './types'
import { emptySecurityFilters, securityFilterParams, type SecurityFilters } from './securityEventFilters'
import './securityEvents.css'

type AuthEvent = {
  id: string; event_time: string; ingested_at: string; event_type: 'LOGIN_FAILED' | 'LOGIN_SUCCEEDED';
  username: string; source_ip: string; destination_ip: string; destination_port: number;
  source_id: string; source_name: string; authentication_method?: string | null; provenance?: string | null
}
type Page = { items: AuthEvent[]; total: number; offset: number; limit: number; has_more: boolean; as_of: string }
type Request = { filters: Record<string, string>; offset: number; limit: number; asOf?: string }
const utc = (value: string) => new Date(value).toISOString().replace('T', ' ')
const outcome = (type: AuthEvent['event_type']) => type === 'LOGIN_FAILED' ? 'Login failed' : 'Login succeeded'

export function SecurityEvents({ sessionKey, refreshKey, sources }: {
  sessionKey: string; refreshKey: number; sources: Source[]
}) {
  const [filters, setFilters] = useState<SecurityFilters>({ ...emptySecurityFilters })
  const [request, setRequest] = useState<Request>({ filters: {}, offset: 0, limit: 25 })
  const [page, setPage] = useState<Page | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [formError, setFormError] = useState('')
  const [selected, setSelected] = useState<AuthEvent | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState('')
  const detailVersion = useRef(0)
  const detailHeading = useRef<HTMLHeadingElement>(null)
  const detailButton = useRef<HTMLButtonElement | null>(null)
  const previousRefresh = useRef(refreshKey)

  useEffect(() => {
    if (previousRefresh.current === refreshKey) return
    previousRefresh.current = refreshKey
    setRequest(current => ({ ...current, offset: 0, asOf: undefined }))
  }, [refreshKey])

  useEffect(() => {
    let active = true
    setLoading(true); setError(''); setPage(null); setSelected(null); setDetailError(''); setDetailLoading(false)
    const params = new URLSearchParams(request.filters)
    params.set('limit', String(request.limit)); params.set('offset', String(request.offset))
    if (request.asOf) params.set('as_of', request.asOf)
    api<Page>(`/api/events/security?${params}`).then(result => {
      if (active) setPage(result)
    }).catch(error => {
      if (active) setError(error instanceof Error ? error.message : 'Could not load security events.')
    }).finally(() => { if (active) setLoading(false) })
    return () => { active = false; detailVersion.current++ }
  }, [request, sessionKey])

  useEffect(() => { if (selected) detailHeading.current?.focus() }, [selected])

  function apply(event: FormEvent) {
    event.preventDefault()
    try {
      const params = securityFilterParams(filters)
      setFormError(''); setRequest(current => ({ filters: params, offset: 0, limit: current.limit }))
    } catch (error) { setFormError(error instanceof Error ? error.message : 'Check your filters.') }
  }
  function update(key: keyof SecurityFilters, value: string) { setFilters(current => ({ ...current, [key]: value })) }
  function move(offset: number) {
    if (page) setRequest(current => ({ ...current, offset, asOf: page.as_of }))
  }
  async function openDetails(event: AuthEvent, button: HTMLButtonElement) {
    const version = ++detailVersion.current
    detailButton.current = button
    setSelected(null); setDetailLoading(true); setDetailError('')
    try {
      const result = await api<AuthEvent>(`/api/events/security/${event.id}`)
      if (detailVersion.current === version) setSelected(result)
    } catch (error) {
      if (detailVersion.current === version) setDetailError(error instanceof Error ? error.message : 'Could not load event details.')
    } finally { if (detailVersion.current === version) setDetailLoading(false) }
  }

  return <section className="panel security-events">
    <div className="panel-heading"><div><h2>Authentication activity</h2><p>Successful and failed logins, whether or not they triggered an incident. Table timestamps are UTC.</p></div></div>
    <form className="security-filters" onSubmit={apply}>
      <label>Outcome<select value={filters.event_type} onChange={event => update('event_type', event.target.value)}><option value="">All outcomes</option><option value="LOGIN_FAILED">Login failed</option><option value="LOGIN_SUCCEEDED">Login succeeded</option></select></label>
      <label>Username (exact)<input maxLength={128} value={filters.username} onChange={event => update('username', event.target.value)} placeholder="e.g. soc-lab-test"/></label>
      <label>Source IP (exact)<input maxLength={45} value={filters.source_ip} onChange={event => update('source_ip', event.target.value)} placeholder="e.g. 10.0.2.2"/></label>
      <label>Destination IP (exact)<input maxLength={45} value={filters.destination_ip} onChange={event => update('destination_ip', event.target.value)} placeholder="e.g. 10.0.2.15"/></label>
      <label>Collector<select value={filters.source_id} onChange={event => update('source_id', event.target.value)}><option value="">All collectors</option>{sources.map(source => <option value={source.id} key={source.id}>{source.name}{source.enabled ? '' : ' (revoked)'}</option>)}</select></label>
      <label>From (your local time)<input type="datetime-local" step="1" value={filters.start_time} onChange={event => update('start_time', event.target.value)}/></label>
      <label>To (your local time)<input type="datetime-local" step="1" value={filters.end_time} onChange={event => update('end_time', event.target.value)}/></label>
      <div className="security-filter-actions"><button className="primary" disabled={loading}>Apply filters</button><button type="button" className="secondary" disabled={loading} onClick={() => {
        setFilters({ ...emptySecurityFilters }); setFormError(''); setRequest(current => ({ filters: {}, offset: 0, limit: current.limit }))
      }}>Clear</button></div>
    </form>
    {formError && <p className="security-feedback login-error" role="alert">{formError}</p>}
    {error && <p className="security-feedback login-error" role="alert">{error}</p>}
    {detailError && <p className="security-feedback login-error" role="alert">{detailError}</p>}
    {detailLoading && <p className="security-feedback" role="status">Loading event details…</p>}
    {selected && <section className="security-event-detail" aria-labelledby="security-detail-heading">
      <div className="panel-heading"><h3 id="security-detail-heading" tabIndex={-1} ref={detailHeading}>Event details</h3><button className="secondary" onClick={() => { setSelected(null); detailButton.current?.focus() }}>Close details</button></div>
      <dl>{[
        ['Outcome', outcome(selected.event_type)], ['Username', selected.username], ['Collector', selected.source_name],
        ['Event time (UTC)', utc(selected.event_time)], ['Event time (local)', new Date(selected.event_time).toLocaleString(undefined, { timeZoneName: 'short' })],
        ['Received by API (UTC)', utc(selected.ingested_at)], ['Source IP', selected.source_ip],
        ['Destination', networkAddress(selected.destination_ip, selected.destination_port)],
        ['Authentication method', selected.authentication_method ?? 'Not recorded'],
        ['Provenance', selected.provenance === 'openssh_journal' ? 'OpenSSH journal' : selected.provenance === 'synthetic_pipeline_test' ? 'Synthetic authentication replay' : 'Not recorded'],
        ['Event ID', selected.id], ['Source ID', selected.source_id],
      ].map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl>
    </section>}
    {loading && <div className="empty" role="status">Loading security events…</div>}
    {!loading && page && <>
      <p className="security-feedback" role="status">{page.total ? `${page.offset + 1}–${page.offset + page.items.length} of ${page.total} authentication records` : 'No authentication records match these filters.'}</p>
      {page.items.length > 0 && <div className="table-wrap"><table><thead><tr><th>Event time (UTC)</th><th>Outcome</th><th>Username</th><th>Source IP</th><th>Destination</th><th>Collector</th><th>Details</th></tr></thead>
        <tbody>{page.items.map(event => <tr key={event.id}>
          <td><time dateTime={event.event_time}>{utc(event.event_time)}</time></td><td><span className={`auth-outcome ${event.event_type === 'LOGIN_FAILED' ? 'failed' : 'succeeded'}`}>{outcome(event.event_type)}</span></td>
          <td>{event.username}</td><td>{event.source_ip}</td><td>{networkAddress(event.destination_ip, event.destination_port)}</td><td>{event.source_name}</td>
          <td><button className="secondary" disabled={detailLoading} onClick={click => void openDetails(event, click.currentTarget)} aria-label={`View event details for ${event.username} at ${event.event_time}`}>Details</button></td>
        </tr>)}</tbody></table></div>}
      <div className="security-pagination"><button className="secondary" disabled={page.offset === 0} onClick={() => move(Math.max(0, page.offset - page.limit))}>Previous</button>
        <span>Page {Math.floor(page.offset / page.limit) + 1}</span><button className="secondary" disabled={!page.has_more} onClick={() => move(page.offset + page.limit)}>Next</button>
        <label>Per page<select value={request.limit} onChange={event => setRequest(current => ({ ...current, limit: Number(event.target.value), offset: 0, asOf: page.as_of }))}>{[25, 50, 100].map(limit => <option key={limit} value={limit}>{limit}</option>)}</select></label>
      </div><p className="security-feedback muted">Pages use a fixed receipt-time snapshot. Refresh to include newly received events. Changing a filter requires Apply filters.</p>
    </>}
  </section>
}
