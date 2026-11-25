export type ReportFormat='html'|'json'
export function reportRequest(incidentId:string,format:ReportFormat,includeAI:boolean) {
  if(!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(incidentId))throw new Error('A private incident ID is required.')
  if(format!=='html'&&format!=='json')throw new Error('Choose HTML or JSON.')
  const id=incidentId.toLowerCase()
  return {path:`/api/incidents/${id}/report?${new URLSearchParams({format,include_ai:String(includeAI)})}`,filename:`aisoc-incident-${id}.${format}`}
}
