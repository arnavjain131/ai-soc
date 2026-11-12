import type { Detail, Stats, Source } from './types'

export const demoIncidents: Detail[] = [
  {
    id: 'demo-auth-001', title: 'Repeated authentication failures against admin', status: 'open', severity: 'high', risk_score: 50,
    score_components: { rule_severity: 40, authentication_evidence: 10 },
    created_at: '2026-11-11T09:32:00Z', updated_at: '2026-11-11T09:32:00Z',
    alerts: [{ id: 'demo-alert-001', rule_key: 'brute_force_v1', explanation: '5 failed logins for the same user, source IP, target, and port within 120 seconds. This is suspicious activity, not proof of compromise.' }],
    events: Array.from({ length: 5 }, (_, i) => ({ id: `demo-event-${i + 1}`, event_time: new Date(Date.UTC(2026, 10, 11, 9, 31) + i * 15000).toISOString(), event_type: 'LOGIN_FAILED', username: 'admin', source_ip: '192.0.2.24', destination_ip: '198.51.100.10', destination_port: 22 })),
  },
  {
    id: 'demo-auth-002', title: 'Repeated authentication failures against service-user', status: 'investigating', severity: 'high', risk_score: 50,
    score_components: { rule_severity: 40, authentication_evidence: 10 },
    created_at: '2026-11-11T08:14:00Z', updated_at: '2026-11-11T08:20:00Z',
    alerts: [{ id: 'demo-alert-002', rule_key: 'brute_force_v1', explanation: 'Five authentication failures in 120 seconds. Review the account owner and source before assigning a disposition.' }],
    events: Array.from({ length: 5 }, (_, i) => ({ id: `demo-event-b-${i + 1}`, event_time: `2026-11-11T08:13:${String(i * 12).padStart(2, '0')}Z`, event_type: 'LOGIN_FAILED', username: 'service-user', source_ip: '192.0.2.90', destination_ip: '198.51.100.15', destination_port: 443 })),
  },
]
export const demoStats: Stats = { events: 10, alerts: 2, incidents: 2, sources: 1, open_incidents: 2 }
export const demoSources: Source[] = [{ id: 'demo-source', name: 'Authentication lab fixture', enabled: true, last_seen: '2026-11-11T09:32:00Z' }]
