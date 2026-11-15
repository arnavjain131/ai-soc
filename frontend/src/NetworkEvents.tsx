import { useEffect, useState } from 'react'
import { api } from './api'
import { networkAddress, type NetworkEvent } from './types'

export function NetworkEvents({ sessionKey, refreshKey }: { sessionKey: string; refreshKey: number }) {
  const [events, setEvents] = useState<NetworkEvent[]>([])
  const [status, setStatus] = useState('Loading network events…')
  useEffect(() => {
    let active = true
    setStatus('Loading network events…')
    api<NetworkEvent[]>('/api/events/network').then(rows => {
      if (!active) return
      setEvents(rows)
      setStatus(rows.length ? '' : 'No network events received yet.')
    }).catch(error => {
      if (!active) return
      setEvents([])
      setStatus(error instanceof Error ? error.message : 'Could not load network events.')
    })
    return () => { active = false }
  }, [sessionKey, refreshKey])

  return <section className="panel">
    <div className="panel-heading"><div><h2>Recent Suricata events</h2></div></div>
    {status && <div className="empty" role="status">{status}</div>}
    {events.length > 0 && <div className="table-wrap"><table>
      <thead><tr><th>UTC Time</th><th>Event</th><th>Source</th><th>Destination</th><th>Protocol</th><th>Collector</th></tr></thead>
      <tbody>{events.map(event => <tr key={event.id}>
        <td><time dateTime={event.event_time}>{new Date(event.event_time).toISOString().replace('T', ' ')}</time></td>
        <td>{event.event_type === 'SURICATA_ALERT'
          ? <>{event.signature}<br/><span className="muted">Signature {event.signature_id} · Suricata severity {event.severity}</span></>
          : 'Network flow'}</td>
        <td>{networkAddress(event.source_ip, event.source_port)}</td>
        <td>{networkAddress(event.destination_ip, event.destination_port)}</td>
        <td>{event.protocol}</td><td>{event.source_name}</td>
      </tr>)}</tbody>
    </table></div>}
  </section>
}
