import { useEffect, useRef, useState } from 'react'

import { ExecutionTimeline } from '../execution-timeline/components/execution-timeline'
import { DecisionControls } from './decision-controls'
import { ProposalEditor } from './proposal-form'
import { useSupportAction } from './use-support-action'

export function ActionPanel({
  reportId,
  onAccessLost,
}: {
  reportId: string
  onAccessLost: () => void
}) {
  const action = useSupportAction(reportId, onAccessLost)
  const { saved } = action
  const p = saved?.proposal
  const previousBinding = useRef<string | undefined>(undefined)
  const [changed, setChanged] = useState(false)
  const binding = saved?.fingerprint ?? undefined
  useEffect(() => {
    if (
      previousBinding.current &&
      binding &&
      previousBinding.current !== binding
    )
      setChanged(true)
    previousBinding.current = binding
  }, [binding])
  return (
    <section className="card mt-8 border-line" aria-labelledby="action-heading">
      <h2 id="action-heading">Proposed action</h2>
      <p className="notice">
        Simulation: no persisted support ticket or external write. Customer
        observations are unconfirmed.
      </p>
      {action.query.isPending && <p role="status">Loading saved action…</p>}
      {action.error && (
        <p role="alert" className="notice-error">
          {action.error}
        </p>
      )}
      {saved && action.query.isError && (
        <p className="notice">
          Showing the last saved action. It may be out of date.
        </p>
      )}
      {!action.online && (
        <p role="status" className="notice">
          Disconnected. Reconnect and refresh before reviewing an action.
        </p>
      )}
      {action.needsRefresh && (
        <p className="notice">
          Your request may have been saved. Refresh saved action before
          continuing.
        </p>
      )}
      {changed && (
        <p role="status" className="notice">
          The proposal changed. Review the current version before deciding.
        </p>
      )}
      {action.mutation.isPending && (
        <p role="status">
          {action.mutation.variables?.kind === 'decide'
            ? 'Submitting decision…'
            : 'Preparing proposal…'}
        </p>
      )}
      {saved?.status === 'absent' && <p>No action is currently proposed.</p>}
      {saved?.archived && (
        <p className="notice">
          This report is archived. Saved outcomes remain readable; new actions
          are blocked.
        </p>
      )}
      {saved?.input_stale && (
        <p className="notice">
          Report state or observations changed since preparation.
          {saved.status === 'awaiting_decision'
            ? ' Revise the undecided proposal before deciding.'
            : ' The saved outcome remains recorded.'}
        </p>
      )}
      {saved?.status === 'absent' && !saved.can_prepare && !saved.archived && (
        <p className="hint">
          Customer intake must finish before support can prepare a proposal.
        </p>
      )}
      {p && (
        <article className="mt-5">
          <h3 className="text-lg font-semibold">
            Create support ticket (create_ticket) · Version {p.version}
          </h3>
          <h4 className="section-title">Exact arguments</h4>
          <dl className="detail-list break-words">
            <dt>Report ID</dt>
            <dd className="break-all">{p.arguments.issue_report_id}</dd>
            <dt>Title</dt>
            <dd>{p.arguments.title}</dd>
            <dt>Description</dt>
            <dd className="whitespace-pre-wrap">{p.arguments.description}</dd>
            <dt>Service</dt>
            <dd>{p.arguments.service_code ?? 'Not specified (null)'}</dd>
            <dt>Tentative incident severity</dt>
            <dd>{p.arguments.severity ?? 'Unknown (null)'}</dd>
          </dl>
          <h4 className="section-title">Why this action</h4>
          <p>{p.explanation}</p>
          <h4 className="section-title">Expected effect</h4>
          <p>{p.expected_effect}</p>
          <h4 className="section-title">Action risk: {p.risk.level}</h4>
          <p>{p.risk.reason}</p>
          <h4 className="section-title">Reversibility</h4>
          <p>
            Simulation has no ticket write to undo. An accepted decision remains
            recorded; this screen does not offer undo or delete.
          </p>
          <details>
            <summary>Technical details</summary>
            <dl className="detail-list break-all">
              <dt>Action ID</dt>
              <dd>{p.action_id}</dd>
              <dt>Fingerprint</dt>
              <dd>{saved.fingerprint}</dd>
              <dt>Idempotency key</dt>
              <dd>{p.idempotency_key}</dd>
            </dl>
          </details>
          <DecisionControls
            key={`${saved.run_id}:${saved.fingerprint}`}
            saved={saved}
            disabled={action.decisionDisabled}
            onDecide={action.decide}
            submitting={
              action.mutation.isPending &&
              action.mutation.variables?.kind === 'decide'
            }
          />
        </article>
      )}
      {saved?.status === 'preparing' && (
        <div className="mt-5">
          <p role="status">
            Proposal preparation is unfinished. It has not approved or executed
            an action.
          </p>
          <button
            className="button-secondary"
            disabled={action.blocked}
            onClick={action.finishPreparation}
          >
            Finish preparing proposal
          </button>
        </div>
      )}
      {saved?.decision && (
        <div className="notice mt-5" role="status">
          <h3 className="font-semibold">
            Saved decision:{' '}
            {saved.decision.decision === 'approve' ? 'Approved' : 'Rejected'}
          </h3>
          <p>
            Proposal version {saved.decision.version} · Actor:{' '}
            <span className="break-all">{saved.decision.actor_id}</span>
          </p>
          <p>
            Decided at:{' '}
            <time dateTime={saved.decision.decided_at}>
              {saved.decision.decided_at}
            </time>
          </p>
          {saved.status === 'rejected' && <p>This action did not execute.</p>}
          {saved.status === 'approved_unconfirmed' && (
            <p>
              Approved; execution is not confirmed. Support review is required.
              Refresh does not retry execution.
            </p>
          )}
          {saved.status === 'execution_unknown' && (
            <p>
              Ticket creation could not be confirmed. The effect is unknown and
              support review is required. No automatic retry.
            </p>
          )}
          {saved.execution && (
            <>
              <p>Simulation; no persisted support ticket was created.</p>
              <p>
                Simulated ticket ID:{' '}
                <span className="break-all">
                  {saved.execution.result.support_ticket_id}
                </span>{' '}
                · Status: {saved.execution.result.status}
              </p>
            </>
          )}
        </div>
      )}
      {action.acceptedPreparation &&
        !action.mutation.isPending &&
        saved?.status !== 'preparing' && (
          <div className="notice mt-5">
            <p>
              A preparation request has an uncertain outcome. Retry its original
              saved fields after refreshing.
            </p>
            <button
              className="button-secondary"
              disabled={action.blocked}
              onClick={action.retryPreparation}
            >
              Retry accepted preparation
            </button>
          </div>
        )}
      {saved?.can_prepare && !action.acceptedPreparation && (
        <ProposalEditor
          key={saved.fingerprint ?? 'new'}
          saved={saved}
          disabled={action.prepareDisabled}
          onPrepare={action.prepare}
        />
      )}
      <button
        className="button-secondary mt-5"
        disabled={action.busy || !action.online}
        onClick={() => void action.refresh()}
      >
        {action.query.isFetching
          ? 'Refreshing action…'
          : 'Refresh saved action'}
      </button>
      {saved && saved.timeline.length > 0 && (
        <div className="mt-8">
          <ExecutionTimeline
            events={saved.timeline}
            heading="Approval timeline"
            id="approval-timeline-heading"
          />
        </div>
      )}
    </section>
  )
}
