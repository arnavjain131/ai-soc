export type NoteRequest = { body: string; request_id: string }

export function prepareNoteRequest(text: string, previous: NoteRequest | null, newId: () => string): NoteRequest {
  const body = text.trim()
  if (!body) throw new Error('Enter a note before saving.')
  if (body.length > 2000) throw new Error('Notes can contain at most 2,000 characters.')
  return previous?.body === body ? previous : { body, request_id: newId() }
}
