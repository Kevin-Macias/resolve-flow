import type { ConnectionState } from '../../workflow-stream/client'
import { intakeErrorMessage } from '../api'
import { useCustomerIntake } from '../use-customer-intake'
import { AcceptedTurns } from './accepted-turns'
import { ClarificationForm } from './clarification-form'

const connectionLabels: Record<ConnectionState, string> = {
  connecting: 'Connecting',
  live: 'Connected',
  reconnecting: 'Reconnecting',
  ended: 'Saved update received',
  unavailable: 'Updates unavailable',
  access_lost: 'Access unavailable',
  protocol_error: 'Update could not be verified',
}
const progressLabels = {
  processing: 'Processing intake',
  waiting_input: 'Waiting for your clarification',
  stage_finished: 'Intake prepared',
  stage_failed: 'Intake failed',
} as const

export function IntakePanel({
  reportId,
  onAccessLost,
}: {
  reportId: string
  onAccessLost: () => void
}) {
  const intake = useCustomerIntake(reportId, onAccessLost)
  const { query, run, snapshot, mutation } = intake
  let error: string | undefined
  if (query.data?.kind === 'unavailable') error = query.data.message
  else if (mutation.isError) error = intakeErrorMessage(mutation.error)
  else if (query.isError) error = intakeErrorMessage(query.error)
  return (
    <section className="card mt-8 border-line" aria-labelledby="intake-heading">
      <h2 id="intake-heading">Customer intake</h2>
      {error && (
        <p role="alert" className="notice-error">
          {error}
        </p>
      )}
      {query.isPending && <p role="status">Loading saved intake…</p>}
      {query.data?.kind === 'absent' && (
        <>
          <p>
            No intake run is currently available. Start intake to review any
            clarification needed for this report.
          </p>
          <button
            className="button-primary"
            disabled={intake.disabled}
            onClick={intake.start}
          >
            {mutation.isPending ? 'Starting intake…' : 'Start intake'}
          </button>
        </>
      )}
      {run && snapshot && (
        <>
          <p className="notice">
            {run.simulated
              ? 'Offline simulation — questions and outcomes follow a demonstration script.'
              : 'Live provider — questions are generated and may need review.'}
          </p>
          <p role="status">
            {progressLabels[snapshot.progress]} · Updates:{' '}
            {connectionLabels[intake.connection]}
          </p>
          <p>{snapshot.customer_update}</p>
          {(intake.connectionFailed || query.isError) && (
            <p className="notice">
              Showing the last saved intake. Refresh to check current state
              before taking another action.
            </p>
          )}
          {intake.needsRefresh && (
            <p className="notice">
              The last action may have been accepted. Refresh saved intake
              before submitting or recovering again.
            </p>
          )}
          {run.incomplete && (
            <p className="notice">Intake continued with incomplete context.</p>
          )}
          <AcceptedTurns turns={run.turns} />
          {run.pending &&
            snapshot.revision === run.revision &&
            snapshot.progress === 'waiting_input' && (
              <ClarificationForm
                key={`${run.run_id}:${run.pending.pending_id}`}
                pending={run.pending}
                disabled={intake.disabled}
                sending={mutation.isPending}
                onReply={intake.reply}
              />
            )}
          {run.status === 'needs_confirmation' && (
            <p>
              Intake is ready for summary confirmation. Confirmation controls
              will be available in a later step; no support ticket has been
              created.
            </p>
          )}
          {run.operation_pending && (
            <div className="mt-5">
              <p>
                An accepted operation is unfinished. This does not tell us
                whether it is still running. If it was interrupted, explicitly
                recover the saved operation.
              </p>
              <button
                className="button-secondary"
                disabled={intake.disabled}
                onClick={intake.recover}
              >
                {mutation.isPending ? 'Working…' : 'Recover saved operation'}
              </button>
            </div>
          )}
        </>
      )}
      <button
        className="button-secondary mt-6"
        disabled={intake.busy}
        onClick={() => void intake.refresh()}
      >
        {query.isFetching ? 'Refreshing intake…' : 'Refresh saved intake'}
      </button>
    </section>
  )
}
