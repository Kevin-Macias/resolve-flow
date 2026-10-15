import { useState, type FormEvent } from 'react'

import {
  proposalFieldsSchema,
  type ProposalFields,
  type SupportAction,
} from './schemas'

export function ProposalEditor({
  saved,
  disabled,
  onPrepare,
}: {
  saved: SupportAction
  disabled: boolean
  onPrepare: (fields: ProposalFields) => void
}) {
  const [editing, setEditing] = useState(!saved.proposal)
  const [title, setTitle] = useState(saved.proposal?.arguments.title ?? '')
  const [description, setDescription] = useState(
    saved.proposal?.arguments.description ?? '',
  )
  const [service, setService] = useState(
    saved.proposal?.arguments.service_code ?? '',
  )
  const [severity, setSeverity] = useState(
    saved.proposal?.arguments.severity ?? '',
  )
  const [explanation, setExplanation] = useState(
    saved.proposal?.explanation ?? '',
  )
  const [error, setError] = useState('')
  if (!editing)
    return (
      <button
        className="button-secondary mt-5"
        disabled={disabled}
        onClick={() => setEditing(true)}
      >
        Revise proposal
      </button>
    )
  function submit(event: FormEvent) {
    event.preventDefault()
    if (disabled) return
    const result = proposalFieldsSchema.safeParse({
      title,
      description,
      service_code: service.trim() || null,
      severity: severity || null,
      explanation,
    })
    if (!result.success) {
      setError(result.error.issues[0]?.message ?? 'Check the proposal fields.')
      return
    }
    setError('')
    onPrepare(result.data)
  }
  return (
    <form className="mt-5" onSubmit={submit}>
      <h3>
        {saved.proposal
          ? 'Revise the undecided proposal'
          : 'Draft a simulated ticket proposal'}
      </h3>
      <p className="hint">
        Support authors these fields from unconfirmed observations. Saving
        prepares review; it does not approve or execute the action.
      </p>
      {error && (
        <p role="alert" className="notice-error">
          {error}
        </p>
      )}
      <fieldset disabled={disabled}>
        <label className="form-label" htmlFor="proposal-title">
          Ticket title
        </label>
        <input
          className="form-field"
          id="proposal-title"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          required
        />
        <label className="form-label" htmlFor="proposal-description">
          Ticket description
        </label>
        <textarea
          className="form-field"
          id="proposal-description"
          rows={5}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          required
        />
        <label className="form-label" htmlFor="proposal-service">
          Service code (optional)
        </label>
        <input
          className="form-field"
          id="proposal-service"
          value={service}
          onChange={(event) => setService(event.target.value)}
        />
        <label className="form-label" htmlFor="proposal-severity">
          Tentative incident severity
        </label>
        <select
          className="form-field"
          id="proposal-severity"
          value={severity}
          onChange={(event) =>
            setSeverity(event.target.value as typeof severity)
          }
        >
          <option value="">Unknown (null)</option>
          <option value="low">Low</option>
          <option value="medium">Medium</option>
          <option value="high">High</option>
          <option value="critical">Critical</option>
        </select>
        <label className="form-label" htmlFor="proposal-explanation">
          Why propose this action?
        </label>
        <textarea
          className="form-field"
          id="proposal-explanation"
          rows={3}
          value={explanation}
          onChange={(event) => setExplanation(event.target.value)}
          required
        />
        <button className="button-primary mt-5" type="submit">
          Save proposal for review
        </button>
        {saved.proposal && (
          <button
            className="button-secondary ml-3"
            type="button"
            onClick={() => setEditing(false)}
          >
            Cancel revision
          </button>
        )}
      </fieldset>
    </form>
  )
}
