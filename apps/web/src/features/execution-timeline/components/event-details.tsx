import type { ExecutionEvent } from '../schemas'

const reasonLabels = {
  missing_data: 'Missing information',
  contradiction: 'Conflicting information',
  low_confidence: 'Low confidence',
  unknown_service: 'Service unknown',
  unknown_severity: 'Severity unknown',
} as const

export function EventDetails({ event }: { event: ExecutionEvent }) {
  const metadata = event.metadata
  const details: [string, string | number][] = []
  if (metadata.round_number != null)
    details.push(['Round', metadata.round_number])
  if (metadata.question_count != null)
    details.push(['Questions', metadata.question_count])
  if (metadata.attempts != null) details.push(['Attempts', metadata.attempts])
  if (metadata.reasons.length)
    details.push([
      'Reasons',
      metadata.reasons.map((reason) => reasonLabels[reason]).join(', '),
    ])
  if (metadata.clarification_cause)
    details.push([
      'Clarification',
      {
        questions_available: 'Questions available',
        no_questions: 'No questions available',
        round_limit: 'Clarification limit reached',
      }[metadata.clarification_cause],
    ])
  if (metadata.extraction_failure)
    details.push([
      'Extraction',
      {
        refusal: 'Provider declined the request',
        empty_output: 'No output returned',
        malformed_json: 'Malformed response',
        invalid_data: 'Invalid response data',
        provider_error: 'Provider unavailable',
      }[metadata.extraction_failure],
    ])
  if (metadata.provider_failure)
    details.push([
      'Provider',
      {
        timeout: 'Timed out',
        transient: 'Temporary failure',
        permanent: 'Permanent failure',
      }[metadata.provider_failure],
    ])
  if (metadata.action_id) details.push(['Action ID', metadata.action_id])
  if (metadata.action_version != null)
    details.push(['Action version', metadata.action_version])
  if (metadata.actor_id) details.push(['Actor ID', metadata.actor_id])
  if (metadata.support_ticket_id)
    details.push([
      metadata.outcome === 'simulated'
        ? 'Simulated ticket ID'
        : 'Result ticket ID',
      metadata.support_ticket_id,
    ])
  if (metadata.fingerprint)
    details.push(['Action fingerprint', metadata.fingerprint])
  return (
    <>
      {(event.event_type === 'continued_incomplete' ||
        metadata.incomplete === true) && (
        <p className="notice">Continued with incomplete context.</p>
      )}
      {metadata.outcome === 'simulated' && (
        <p className="notice">
          Simulated outcome. No real support ticket was created.
        </p>
      )}
      {metadata.outcome === 'unknown' && (
        <p className="notice-error">
          The effect is unknown. Check the outcome before any further action.
        </p>
      )}
      {details.length > 0 && (
        <dl className="mt-3 grid gap-3 sm:grid-cols-2">
          {details.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      )}
    </>
  )
}
