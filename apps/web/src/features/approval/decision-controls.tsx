import { useEffect, useRef, useState } from 'react'

import type { DecisionRequest, SupportAction } from './schemas'

export function DecisionControls({
  saved,
  disabled,
  onDecide,
  submitting = false,
}: {
  saved: SupportAction
  disabled: boolean
  onDecide: (body: DecisionRequest) => void
  submitting?: boolean
}) {
  const [choice, setChoice] = useState<'approve' | 'reject'>()
  const [closedMessage, setClosedMessage] = useState('')
  const heading = useRef<HTMLHeadingElement>(null)
  const approvalTrigger = useRef<HTMLButtonElement>(null)
  const rejectionTrigger = useRef<HTMLButtonElement>(null)
  const proposal = saved.proposal
  useEffect(() => {
    if (disabled && choice) {
      setChoice(undefined)
      setClosedMessage(
        submitting
          ? ''
          : 'Review was interrupted. Refresh saved action and review again.',
      )
    }
  }, [disabled, choice, submitting])
  useEffect(() => {
    if (choice) heading.current?.focus()
  }, [choice])
  function cancel() {
    const trigger = choice === 'approve' ? approvalTrigger : rejectionTrigger
    setChoice(undefined)
    requestAnimationFrame(() => trigger.current?.focus())
  }
  const fingerprint = saved.fingerprint
  if (!proposal || !fingerprint || saved.status !== 'awaiting_decision')
    return null
  return (
    <div className="mt-5">
      {closedMessage && (
        <p role="status" className="notice">
          {closedMessage}
        </p>
      )}
      {choice ? (
        <div
          className="notice"
          role="group"
          aria-labelledby="decision-confirmation-heading"
        >
          <h3
            id="decision-confirmation-heading"
            ref={heading}
            tabIndex={-1}
            className="font-semibold"
          >
            {choice === 'approve'
              ? `Approve version ${proposal.version} and allow the simulated ticket action?`
              : `Reject version ${proposal.version}? This action will not execute.`}
          </h3>
          <button
            className="button-primary"
            disabled={disabled}
            onClick={() =>
              onDecide({
                action_id: proposal.action_id,
                version: proposal.version,
                fingerprint,
                decision: choice,
              })
            }
          >
            {choice === 'approve' ? 'Approve' : 'Reject'} version{' '}
            {proposal.version}
          </button>
          <button
            className="button-secondary ml-3"
            disabled={disabled}
            onClick={cancel}
          >
            Keep reviewing
          </button>
        </div>
      ) : null}
      <div className="mt-3 flex flex-wrap gap-3">
        <button
          className="button-primary"
          ref={approvalTrigger}
          disabled={disabled || Boolean(choice)}
          onClick={() => {
            setClosedMessage('')
            setChoice('approve')
          }}
        >
          Review approval
        </button>
        <button
          className="button-secondary"
          ref={rejectionTrigger}
          disabled={disabled || Boolean(choice)}
          onClick={() => {
            setClosedMessage('')
            setChoice('reject')
          }}
        >
          Review rejection
        </button>
      </div>
    </div>
  )
}
