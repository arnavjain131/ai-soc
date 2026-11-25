import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { api } from './api'
import { prepareNoteRequest, type NoteRequest } from './incidentNoteRequest'
import './incidentJournal.css'

type Entry = { id: string; actor_id: string; created_at: string }
type Note = Entry & { body: string }
type History = Entry & { action: string; details: { before?: string | null; after?: string | null } }
type Page<T> = { items: T[]; total: number; offset: number; limit: number; has_more: boolean }
const localTime = (timestamp: string) => new Date(timestamp).toLocaleString(undefined, { timeZoneName: 'short' })
const statusName = (value?: string | null) => value?.replaceAll('_', ' ') ?? 'Unknown'

export function IncidentJournal({ incidentId, viewerId, refreshKey }: {
  incidentId: string; viewerId?: string; refreshKey: string
}) {
  const [body, setBody] = useState('')
  const [noteOffset, setNoteOffset] = useState(0)
  const [historyOffset, setHistoryOffset] = useState(0)
  const [revision, setRevision] = useState(0)
  const [notes, setNotes] = useState<Page<Note> | null>(null)
  const [history, setHistory] = useState<Page<History> | null>(null)
  const [notesLoading, setNotesLoading] = useState(true)
  const [historyLoading, setHistoryLoading] = useState(true)
  const [notesError, setNotesError] = useState('')
  const [historyError, setHistoryError] = useState('')
  const [saveError, setSaveError] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState('')
  const retryRequest = useRef<NoteRequest | null>(null)
  const live = useRef(true)
  const submitting = useRef(false)

  useEffect(() => { live.current = true; return () => { live.current = false } }, [])
  useEffect(() => {
    let active = true
    setNotesLoading(true); setNotesError(''); setNotes(null)
    api<Page<Note>>(`/api/incidents/${incidentId}/notes?limit=10&offset=${noteOffset}`).then(result => {
      if (active) setNotes(result)
    }).catch(error => { if (active) setNotesError(error instanceof Error ? error.message : 'Could not load notes.') })
      .finally(() => { if (active) setNotesLoading(false) })
    return () => { active = false }
  }, [incidentId, noteOffset, revision, refreshKey])
  useEffect(() => {
    let active = true
    setHistoryLoading(true); setHistoryError(''); setHistory(null)
    api<Page<History>>(`/api/incidents/${incidentId}/audit?limit=10&offset=${historyOffset}`).then(result => {
      if (active) setHistory(result)
    }).catch(error => { if (active) setHistoryError(error instanceof Error ? error.message : 'Could not load audit history.') })
      .finally(() => { if (active) setHistoryLoading(false) })
    return () => { active = false }
  }, [incidentId, historyOffset, revision, refreshKey])

  async function save(event: FormEvent) {
    event.preventDefault()
    if (submitting.current) return
    setSaveError(''); setSaved('')
    let request: NoteRequest
    try {
      request = prepareNoteRequest(body, retryRequest.current, () => crypto.randomUUID())
    } catch (error) { setSaveError(error instanceof Error ? error.message : 'Check the note.'); return }
    retryRequest.current = request
    submitting.current = true; setSaving(true)
    try {
      await api<Note>(`/api/incidents/${incidentId}/notes`, 'POST', request)
      if (!live.current) return
      retryRequest.current = null; setBody(''); setSaved('Note saved to the incident history.')
      setNoteOffset(0); setHistoryOffset(0); setRevision(value => value + 1)
    } catch (error) {
      if (live.current) setSaveError((error instanceof Error ? error.message : 'Could not save the note.') + ' If the connection failed, retrying unchanged text will not add a duplicate.')
    } finally {
      submitting.current = false
      if (live.current) setSaving(false)
    }
  }
  function actor(entry: Entry) { return entry.actor_id === viewerId ? 'You' : `Member ${entry.actor_id.slice(0, 8)}` }

  return <div className="incident-journal">
    <section className="panel">
      <div className="panel-heading"><div><h2>Analyst notes</h2><p>Shared with authorized workspace members. Notes cannot be edited or deleted in this release.</p></div></div>
      <form className="journal-note-form" onSubmit={event => void save(event)}>
        <label htmlFor="incident-note">Add an investigation note</label>
        <textarea id="incident-note" value={body} maxLength={2000} rows={4} disabled={saving} onChange={event => { setBody(event.target.value); setSaved('') }} placeholder="Record your findings, evidence references or next investigation steps."/>
        <div className="journal-form-actions"><span className="muted">{body.length}/2,000 characters</span><button className="primary" disabled={saving || !body.trim()}>{saving ? 'Saving…' : 'Save note'}</button></div>
        {saveError && <p className="login-error" role="alert">{saveError}</p>}{saved && <p className="journal-success" role="status">{saved}</p>}
      </form>
      {notesLoading && <p className="journal-feedback" role="status">Loading analyst notes…</p>}
      {notesError && <p className="journal-feedback login-error" role="alert">{notesError}</p>}
      {notes && <>
        {!notes.total && <p className="journal-feedback">No analyst notes yet.</p>}
        <ol className="journal-entries">{notes.items.map(note => <li key={note.id}>
          <div className="journal-entry-meta"><strong title={note.actor_id}>{actor(note)}</strong><time dateTime={note.created_at} title={note.created_at}>{localTime(note.created_at)}</time></div>
          <p className="journal-note-body">{note.body}</p>
        </li>)}</ol>
        {notes.total > 10 && <div className="journal-pagination"><button className="secondary" disabled={!noteOffset} onClick={() => setNoteOffset(value => Math.max(0, value - 10))}>Newer notes</button><span>{noteOffset + 1}–{noteOffset + notes.items.length} of {notes.total}</span><button className="secondary" disabled={!notes.has_more} onClick={() => setNoteOffset(value => value + 10)}>Older notes</button></div>}
      </>}
    </section>
    <section className="panel">
      <div className="panel-heading"><div><h2>Incident audit history</h2><p>Recorded analyst notes, status and assignment changes, newest first.</p></div><button className="secondary" disabled={notesLoading || historyLoading || saving} onClick={() => setRevision(value => value + 1)}>Refresh history</button></div>
      {historyLoading && <p className="journal-feedback" role="status">Loading audit history…</p>}
      {historyError && <p className="journal-feedback login-error" role="alert">{historyError}</p>}
      {history && <>
        {!history.total && <p className="journal-feedback">No analyst actions have been recorded for this incident.</p>}
        <ol className="journal-entries">{history.items.map(entry => <li key={entry.id}>
          <div className="journal-entry-meta"><strong title={entry.actor_id}>{actor(entry)}</strong><time dateTime={entry.created_at} title={entry.created_at}>{localTime(entry.created_at)}</time></div>
          <p>{entry.action === 'incident.note_added' ? 'Added an analyst note.' : entry.action==='incident.assignment_changed' ? `Changed assignee from ${entry.details.before||'Unassigned'} to ${entry.details.after||'Unassigned'}.` : `Changed status from ${statusName(entry.details.before)} to ${statusName(entry.details.after)}.`}</p>
        </li>)}</ol>
        {history.total > 10 && <div className="journal-pagination"><button className="secondary" disabled={!historyOffset} onClick={() => setHistoryOffset(value => Math.max(0, value - 10))}>Newer actions</button><span>{historyOffset + 1}–{historyOffset + history.items.length} of {history.total}</span><button className="secondary" disabled={!history.has_more} onClick={() => setHistoryOffset(value => value + 10)}>Older actions</button></div>}
      </>}
    </section>
  </div>
}
