export type IncidentStatus = 'open' | 'investigating' | 'closed' | 'false_positive'
export type SecurityEvent = { id: string; event_time: string; event_type: string; username: string; source_ip: string; destination_ip: string; destination_port: number }
export type NetworkEvent = {
  id: string
  event_time: string
  event_type: 'NETWORK_FLOW' | 'SURICATA_ALERT'
  source_ip: string
  source_port: number
  destination_ip: string
  destination_port: number
  protocol: 'TCP' | 'UDP'
  source_name: string
  signature_id?: number
  signature?: string
  severity?: number
}
export function networkAddress(ip: string, port: number) {
  return ip.includes(':') ? `[${ip}]:${port}` : `${ip}:${port}`
}
export type Incident = {
  id: string; title: string; status: IncidentStatus; severity: string; risk_score: number;
  score_components: Record<string, number>; created_at: string; updated_at: string;
}
export type Detail = Incident & {
  alerts: { id: string; rule_key: string; explanation: string }[]
  events: SecurityEvent[]
  related_network_events?: NetworkEvent[]
}
export type Stats = { events: number; alerts: number; incidents: number; sources: number; open_incidents: number }
export type Source = { id: string; name: string; enabled: boolean; last_seen: string | null }
