export type IncidentStatus = 'open' | 'investigating' | 'closed' | 'false_positive'
export type SecurityEvent = { id: string; event_time: string; event_type: string; username: string; source_ip: string; destination_ip: string; destination_port: number }
export type Incident = {
  id: string; title: string; status: IncidentStatus; severity: string; risk_score: number;
  score_components: Record<string, number>; created_at: string; updated_at: string;
}
export type Detail = Incident & { alerts: { id: string; rule_key: string; explanation: string }[]; events: SecurityEvent[] }
export type Stats = { events: number; alerts: number; incidents: number; sources: number; open_incidents: number }
export type Source = { id: string; name: string; enabled: boolean; last_seen: string | null }
