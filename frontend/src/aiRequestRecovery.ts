export type AIRequestReceipt<A> = {
  state: 'not_found' | 'pending' | 'completed' | 'failed'
  analysis?: A
  error_code?: string
}

export function aiFailureMessage(code?: string): string {
  const validation = ['invalid_provider_output', 'invalid_provider_json', 'invalid_answer_json',
    'invalid_answer_schema', 'invalid_evidence_citation', 'invalid_reference_citation',
    'oversized_answer', 'unexpected_provider_output']
  const reason = validation.includes(code || '')
    ? 'The model response failed format or evidence validation and was rejected.'
    : code === 'provider_configuration' ? 'The provider rejected the server configuration or API key.'
    : code === 'provider_rate_limited' ? 'The provider reported a rate or billing limit.'
    : code === 'provider_refused' ? 'The provider declined to produce an analysis.'
    : ['provider_incomplete', 'provider_response_limit'].includes(code || '')
      ? 'The provider response was incomplete or exceeded the response limit.'
      : 'The provider request could not be completed.'
  return `${reason} This attempt counts toward quota. Refreshing checks saved status only; it cannot repair a failed generation. A new attempt is optional and uses quota.`
}

// GET-only recovery: never retry generation or allocate a new request ID here.
export async function recoverAIRequest<T extends { request?: AIRequestReceipt<unknown> | null }>(
  read: () => Promise<T>,
  onSnapshot: (snapshot: T) => void,
  active: () => boolean,
  sleep: (ms: number) => Promise<void> = ms => new Promise(resolve => setTimeout(resolve, ms)),
): Promise<'completed' | 'failed' | 'unconfirmed' | 'cancelled'> {
  for (const delay of [0, 1000, 2000, 4000, 8000, 10000]) {
    if (!active()) return 'cancelled'
    if (delay) await sleep(delay)
    if (!active()) return 'cancelled'
    let snapshot: T
    try { snapshot = await read() } catch (error) {
      if (!active()) return 'cancelled'
      const status = (error as {status?: number})?.status
      if (status && [401, 403, 404].includes(status)) throw error
      continue
    }
    if (!active()) return 'cancelled'
    onSnapshot(snapshot)
    if (snapshot.request?.state === 'completed' && snapshot.request.analysis) return 'completed'
    if (snapshot.request?.state === 'failed') return 'failed'
  }
  return 'unconfirmed'
}
