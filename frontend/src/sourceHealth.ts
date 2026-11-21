import type { Source } from './types'

export const STALE_AFTER_MS = 15 * 60 * 1000
export type Freshness = 'recent' | 'stale' | 'never' | 'revoked' | 'unknown'

export function sourceFreshness(source: Source, now: number): Freshness {
  if (!source.enabled) return 'revoked'
  if (source.last_seen === null) return 'never'
  const timestamp = Date.parse(source.last_seen)
  if (!Number.isFinite(timestamp) || timestamp > now + 2 * 60 * 1000) return 'unknown'
  return now - timestamp >= STALE_AFTER_MS ? 'stale' : 'recent'
}

export function receiptAge(timestamp: string, now: number): string {
  const parsed = Date.parse(timestamp)
  if (!Number.isFinite(parsed)) return 'Unknown time'
  const seconds = Math.max(0, Math.floor((now - parsed) / 1000))
  if (seconds < 60) return 'Less than a minute ago'
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} hr ago`
  return `${Math.floor(seconds / 86400)} days ago`
}
