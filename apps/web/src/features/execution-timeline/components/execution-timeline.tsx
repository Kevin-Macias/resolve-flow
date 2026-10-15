import type { ExecutionEvent } from '../schemas'
import { EventDetails } from './event-details'

const eventLabels: Record<ExecutionEvent['event_type'], string> = {
  workflow_started: 'Intake started',
  extraction_succeeded: 'Report information extracted',
  extraction_failed: 'Report extraction failed',
  clarification_evaluated: 'Clarification evaluated',
  clarification_requested: 'Customer clarification requested',
  clarification_answered: 'Customer clarification answered',
  continued_incomplete: 'Continued with incomplete context',
  diagnosis_prepared: 'Preliminary diagnosis prepared',
  report_ready: 'Intake report prepared',
  approval_requested: 'Action approval requested',
  action_approved: 'Action approved',
  action_rejected: 'Action rejected',
  tool_succeeded: 'Tool execution succeeded',
  tool_failed: 'Tool execution failed',
}

export function ExecutionTimeline({
  events,
  loading = false,
  error,
  stale = false,
  unavailable = false,
  heading = 'Execution timeline',
  id = 'timeline-heading',
}: {
  events: readonly ExecutionEvent[]
  loading?: boolean
  error?: string
  stale?: boolean
  unavailable?: boolean
  heading?: string
  id?: string
}) {
  return (
    <section aria-labelledby={id}>
      <h2 id={id}>{heading}</h2>
      {unavailable ? (
        <p role="alert" className="notice-error">
          {error ?? 'Timeline unavailable.'}
        </p>
      ) : loading ? (
        <p role="status">Loading saved timeline…</p>
      ) : (
        <>
          {error && (
            <p role="alert" className="notice-error">
              {error}
            </p>
          )}
          {stale && (
            <p role="status" className="notice">
              Showing the last loaded history. It may be out of date.
            </p>
          )}
          {events.length === 0 ? (
            !error && (
              <p>
                No saved events yet. An empty history does not establish whether
                analysis has finished.
              </p>
            )
          ) : (
            <ol aria-label="Saved execution events" className="space-y-4">
              {events.map((event) => (
                <li key={event.event_id} className="card border-line">
                  <p className="eyebrow mt-0">
                    {event.stage === 'intake' ? 'Intake' : 'Approval'} · Step{' '}
                    {event.sequence}
                  </p>
                  <h3 className="font-semibold">
                    {eventLabels[event.event_type]}
                  </h3>
                  <time
                    dateTime={event.occurred_at}
                    className="text-sm text-muted"
                  >
                    {event.occurred_at}
                  </time>
                  {event.event_type === 'report_ready' && (
                    <p>
                      The intake report is ready for confirmation. This does not
                      mean a support ticket was created or the issue resolved.
                    </p>
                  )}
                  {event.event_type === 'action_approved' && (
                    <p>
                      The decision was saved. Tool execution is a separate
                      outcome.
                    </p>
                  )}
                  <EventDetails event={event} />
                </li>
              ))}
            </ol>
          )}
        </>
      )}
    </section>
  )
}
