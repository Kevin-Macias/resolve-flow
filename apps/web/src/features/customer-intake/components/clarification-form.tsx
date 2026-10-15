import { useState, type FormEvent } from 'react'

import { answersSchema, type CustomerRun } from '../schemas'

export function ClarificationForm({
  pending,
  disabled,
  sending,
  onReply,
}: {
  pending: NonNullable<CustomerRun['pending']>
  disabled: boolean
  sending: boolean
  onReply: (action: 'answer' | 'continue_incomplete', answers: string[]) => void
}) {
  const [answers, setAnswers] = useState(() => pending.questions.map(() => ''))
  const [invalid, setInvalid] = useState(false)
  const [confirmContinue, setConfirmContinue] = useState(false)
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (disabled) return
    const parsed = answersSchema.safeParse(answers)
    setInvalid(!parsed.success)
    if (parsed.success && parsed.data.length === pending.questions.length)
      onReply('answer', parsed.data)
  }
  return (
    <div>
      <h3 className="mt-5 font-semibold">Current clarification</h3>
      {pending.round_number !== null && (
        <p className="hint">Round {pending.round_number} of 2</p>
      )}
      {pending.mode === 'answer_or_continue' ? (
        <form onSubmit={submit} noValidate>
          {pending.questions.map((question, index) => (
            <div key={index}>
              <label className="form-label" htmlFor={`intake-answer-${index}`}>
                {question}
              </label>
              <textarea
                id={`intake-answer-${index}`}
                className="form-field"
                rows={3}
                value={answers[index]}
                disabled={disabled}
                aria-invalid={invalid}
                aria-describedby={invalid ? 'intake-answer-error' : undefined}
                onChange={(event) =>
                  setAnswers((previous) =>
                    previous.map((answer, position) =>
                      position === index ? event.target.value : answer,
                    ),
                  )
                }
              />
              <p className="hint">
                {[...answers[index]].length} / 2,000 characters
              </p>
            </div>
          ))}
          {invalid && (
            <p id="intake-answer-error" role="alert" className="notice-error">
              Answer every question with between 1 and 2,000 characters.
            </p>
          )}
          <button className="button-primary" type="submit" disabled={disabled}>
            {sending ? 'Submitting…' : 'Submit answers'}
          </button>
        </form>
      ) : (
        <p>
          {pending.cause === 'round_limit'
            ? 'The clarification limit has been reached. You can continue with incomplete context.'
            : 'No further questions are available. You can continue with incomplete context.'}
        </p>
      )}
      {confirmContinue ? (
        <div className="notice mt-5">
          <p>
            Your unsent answers will not be submitted. Continue with the
            information already saved?
          </p>
          <div className="form-actions">
            <button
              className="button-primary"
              disabled={disabled}
              onClick={() => {
                if (!disabled) onReply('continue_incomplete', [])
              }}
            >
              Confirm incomplete continuation
            </button>
            <button
              className="button-secondary"
              disabled={sending}
              onClick={() => setConfirmContinue(false)}
            >
              Keep reviewing
            </button>
          </div>
        </div>
      ) : (
        <button
          className="button-secondary mt-5"
          disabled={disabled}
          onClick={() => setConfirmContinue(true)}
        >
          Continue with incomplete context
        </button>
      )}
    </div>
  )
}
