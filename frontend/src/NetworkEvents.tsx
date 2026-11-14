import { useEffect, useState } from 'react'
import { api } from './api'

type NetworkEvent = {
  id: string
  event_time: string
  source_ip: string
  source_port: number
  destination_ip: string
  destination_port: number
  protocol: 'TCP' | 'UDP'
  source_name: string
}

function address(ip: string, port: number) {
  return ip.includes(':') ? `[${ip}]:${port}` : `${ip}:${port}`
}

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
    <div className="panel-heading"><div><h2>Recent network flows</h2><p>TCP and UDP connection records received from Suricata.</p></div></div>
    {status && <div className="empty" role="status">{status}</div>}
    {events.length > 0 && <div className="table-wrap"><table>
      <thead><tr><th>UTC Time</th><th>Source</th><th>Destination</th><th>Protocol</th><th>Collector</th></tr></thead>
      <tbody>{events.map(event => <tr key={event.id}>
        <td><time dateTime={event.event_time}>{new Date(event.event_time).toISOString().replace('T', ' ')}</time></td>
        <td>{address(event.source_ip, event.source_port)}</td>
        <td>{address(event.destination_ip, event.destination_port)}</td>
        <td>{event.protocol}</td><td>{event.source_name}</td>
      </tr>)}</tbody>
    </table></div>}
  </section>
}
