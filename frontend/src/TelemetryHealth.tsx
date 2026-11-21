import type { Source } from './types'
import { receiptAge, sourceFreshness, type Freshness } from './sourceHealth'
import './sourceHealth.css'

const labels: Record<Freshness, string> = {
  recent: 'Recent contact', stale: 'Stale', never: 'Never received', revoked: 'Revoked', unknown: 'Check timestamp',
}

export function SourceStatus({ source, now, demo }: { source: Source; now: number; demo: boolean }) {
  const status = sourceFreshness(source, now)
  const timestamp = source.last_seen && Number.isFinite(Date.parse(source.last_seen)) ? source.last_seen : null
  return <div className="source-status">
    <span className={`freshness-badge ${demo ? 'fixture' : status}`}>{demo ? 'Demo fixture' : labels[status]}</span>
    <p>{demo ? 'Sample contact time' : 'Last ingestion contact'}{timestamp && !demo ? ` · ${receiptAge(timestamp, now)}` : ''}</p>
    {timestamp ? <>
      <time dateTime={timestamp}>{new Date(timestamp).toLocaleString(undefined, { timeZoneName: 'short' })}</time>
      <span className="source-utc">{new Date(timestamp).toISOString().replace('T', ' ')} UTC</span>
    </> : <span className="source-utc">{source.last_seen === null ? 'No ingestion contact recorded' : 'Timestamp unavailable'}</span>}
  </div>
}

export function SourceHealth({ sources, now, checkedAt, onReview }: {
  sources: Source[]; now: number; checkedAt: number | null; onReview: () => void
}) {
  const counts: Record<Freshness, number> = { recent: 0, stale: 0, never: 0, revoked: 0, unknown: 0 }
  sources.forEach(source => counts[sourceFreshness(source, now)]++)
  const needsReview = counts.stale + counts.unknown
  return <section className={`panel source-health ${needsReview ? 'needs-review' : ''}`} aria-label="Telemetry freshness">
    <div className="panel-heading"><div><h2>Telemetry freshness</h2>
      <p>{sources.length ? 'Recent contact means an ingestion request within 15 minutes.' : 'No telemetry sources registered yet.'}</p>
    </div><button className="secondary source-review" onClick={onReview}>Review sources</button></div>
    <div className="source-health-counts">{(Object.keys(counts) as Freshness[]).map(status =>
      <span key={status} className={`freshness-badge ${status}`}><strong>{counts[status]}</strong> {labels[status]}</span>)}</div>
    {needsReview > 0 && <p className="source-health-notice" role="status">{needsReview} source(s) need review. Check the collector and its delivery logs if you expected new traffic.</p>}
    <p className="source-health-help">Stale means no ingestion contact for at least 15 minutes. An idle or intentionally stopped lab may be stale; this does not prove the collector is offline. Queue depth and service status are not reported here.</p>
    <p className="source-health-help">{checkedAt ? `Source snapshot checked ${receiptAge(new Date(checkedAt).toISOString(), now).toLowerCase()}. ` : ''}Use Refresh to fetch current source information. Ages use your computer’s clock.</p>
  </section>
}
