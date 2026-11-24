export type AIRequestReceipt<A> = {
  state: 'not_found' | 'pending' | 'completed' | 'failed'
  analysis?: A
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
