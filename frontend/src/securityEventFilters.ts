export type SecurityFilters = {
  event_type: string; username: string; source_ip: string; destination_ip: string;
  source_id: string; start_time: string; end_time: string
}
export const emptySecurityFilters: SecurityFilters = {
  event_type: '', username: '', source_ip: '', destination_ip: '', source_id: '', start_time: '', end_time: '',
}
export function securityFilterParams(filters: SecurityFilters): Record<string, string> {
  const result: Record<string, string> = {}
  for (const key of ['event_type', 'username', 'source_ip', 'destination_ip', 'source_id'] as const) {
    const value = filters[key].trim()
    if (value) result[key] = value
  }
  for (const key of ['start_time', 'end_time'] as const) {
    if (filters[key]) {
      const date = new Date(filters[key])
      if (!Number.isFinite(date.getTime())) throw new Error('Enter valid start and end times.')
      result[key] = date.toISOString()
    }
  }
  if (result.start_time && result.end_time && result.start_time > result.end_time) {
    throw new Error('Start time must not be after end time.')
  }
  return result
}
