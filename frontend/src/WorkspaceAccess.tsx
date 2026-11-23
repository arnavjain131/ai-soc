import { useEffect, useRef, useState } from 'react'
import { api, ApiError } from './api'
import './workspaceAccess.css'

type Member = { user_id: string; role: string; is_self: boolean }
type History = { id: string; actor: string; action: string; user_id: string; role: string | null; created_at: string }
type Page<T> = { items: T[]; total: number; offset: number; has_more: boolean }
type Members = Page<Member> & { admin_count: number }

export function WorkspaceAccess({ refreshKey }: { refreshKey: number }) {
  const [members, setMembers] = useState<Members | null>(null), [history, setHistory] = useState<Page<History> | null>(null)
  const [offset, setOffset] = useState(0), [auditOffset, setAuditOffset] = useState(0)
  const [loading, setLoading] = useState(true), [saving, setSaving] = useState(false)
  const [error, setError] = useState(''), [notice, setNotice] = useState(''), [selected, setSelected] = useState<Member | null>(null)
  const [confirmation, setConfirmation] = useState(''), [revision, setRevision] = useState(0)
  const current = useRef(0), submitting = useRef(false)
  useEffect(() => {
    const request = ++current.current
    setLoading(true); setError(''); setSelected(null); setConfirmation('')
    void Promise.all([api<Members>(`/api/members?limit=25&offset=${offset}`),
      api<Page<History>>(`/api/members/audit?limit=25&offset=${auditOffset}`)]).then(([people,audit]) => {
      if (current.current === request) { setMembers(people); setHistory(audit) }
    }).catch(failure => {
      if (current.current !== request) return
      setMembers(null); setHistory(null)
      setError(failure instanceof ApiError && failure.status === 404 ? 'Workspace access management requires the latest API deployment.'
        : failure instanceof Error ? failure.message : 'Could not load workspace access.')
    }).finally(() => { if (current.current === request) setLoading(false) })
    return () => { current.current += 1 }
  }, [offset,auditOffset,refreshKey,revision])

  async function revoke() {
    if (!selected || confirmation !== selected.user_id || submitting.current) return
    submitting.current = true; setSaving(true); setError(''); setNotice('')
    const request = current.current, target = selected.user_id
    try {
      await api(`/api/members/${target}`,'DELETE')
      if (current.current !== request) return
      setNotice('Workspace access revoked. The Auth account and historical security records were retained.')
      setSelected(null); setConfirmation(''); setOffset(0); setAuditOffset(0); setRevision(value => value + 1)
    } catch (failure) {
      if (current.current === request) setError(failure instanceof Error ? failure.message : 'Could not revoke access. Refresh before retrying.')
    } finally { submitting.current = false; if (current.current === request) setSaving(false) }
  }

  return <div className="workspace-access">
    <section className="panel access-intro"><h2>Workspace access</h2><p>Administrators can review members and revoke workspace access. The project owner provisions new approved analysts.</p><p>Removing membership preserves the Auth account, incidents and evidence. Collector credentials are managed separately under Telemetry sources.</p></section>
    {error && <p className="feedback error" role="alert">{error}</p>}{notice && <p className="feedback" role="status">{notice}</p>}
    {loading && <p role="status">Loading workspace access…</p>}
    {members && !loading && <section className="panel"><div className="panel-heading"><h2>Members</h2><span>{members.total} total · {members.admin_count} administrator(s)</span></div>
      <div className="access-table"><table><thead><tr><th>Account ID</th><th>Role</th><th>Access</th></tr></thead><tbody>{members.items.map(member => <tr key={member.user_id}>
        <td><code>{member.user_id}</code>{member.is_self && <span> · You</span>}</td><td>{member.role}</td><td>
          {member.is_self ? 'Your own access is protected' : member.role === 'admin' && members.admin_count <= 1 ? 'Last administrator protected'
            : <button className="quiet" disabled={saving} onClick={() => { setSelected(member); setConfirmation(''); setError(''); setNotice('') }}>Review revocation</button>}
        </td></tr>)}</tbody></table></div>
      <div className="access-pagination"><button disabled={saving || !offset} onClick={() => setOffset(value => Math.max(0,value-25))}>Previous</button><span>{members.total ? `${offset+1}–${Math.min(offset+25,members.total)} of ${members.total}` : 'No members'}</span><button disabled={saving || !members.has_more} onClick={() => setOffset(value => value+25)}>Next</button></div>
    </section>}
    {selected && !loading && <section className="panel access-intro" role="region" aria-labelledby="revoke-title"><h2 id="revoke-title">Confirm workspace revocation</h2>
      <p>Remove {selected.role} access for <code>{selected.user_id}</code>? Subsequent private API requests will be denied. Previously downloaded data and collector credentials are unaffected.</p>
      <label htmlFor="revoke-confirmation">Type the full account ID to confirm</label><input id="revoke-confirmation" autoComplete="off" value={confirmation} disabled={saving} onChange={event => setConfirmation(event.target.value)}/>
      <div className="access-actions"><button className="primary" disabled={saving || confirmation !== selected.user_id} onClick={() => void revoke()}>{saving ? 'Revoking…' : 'Revoke workspace access'}</button><button disabled={saving} onClick={() => { setSelected(null); setConfirmation('') }}>Cancel</button></div>
    </section>}
    {history && !loading && <section className="panel"><div className="panel-heading"><h2>Access audit history</h2></div><div className="access-history">
      {!history.total && <p>No recorded membership changes. Older provisioning may predate this audit feature.</p>}
      {history.items.map(item => <article key={item.id}><strong>{item.action === 'membership.granted' ? 'Access granted' : 'Access revoked'} · {item.role ?? 'Unrecorded role'}</strong>
        <p>Account <code>{item.user_id}</code></p><p>By <code>{item.actor}</code> · <time dateTime={item.created_at} title={item.created_at}>{new Date(item.created_at).toLocaleString()}</time></p></article>)}
    </div><div className="access-pagination"><button disabled={saving || !auditOffset} onClick={() => setAuditOffset(value => Math.max(0,value-25))}>Previous</button><span>{history.total} recorded change(s)</span><button disabled={saving || !history.has_more} onClick={() => setAuditOffset(value => value+25)}>Next</button></div></section>}
  </div>
}
