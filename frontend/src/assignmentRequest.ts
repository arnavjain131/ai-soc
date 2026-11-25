export type AssignmentRequest={assignee_id:string|null;expected_revision:string|null;request_id:string}
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
export function memberUUID(value:string):string {
  if(!uuid.test(value.trim()))throw new Error('Enter a complete member account UUID.')
  return value.trim().toLowerCase()
}
export function prepareAssignmentRequest(assignee:string|null,revision:string|null,previous:AssignmentRequest|null,newId:()=>string):AssignmentRequest {
  const target=assignee ? memberUUID(assignee) : null,expected=revision ? memberUUID(revision) : null
  if(previous?.assignee_id===target && previous.expected_revision===expected)return previous
  return {assignee_id:target,expected_revision:expected,request_id:newId()}
}
