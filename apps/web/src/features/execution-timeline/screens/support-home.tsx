import { useNavigate } from '@tanstack/react-router'
import { useState, type FormEvent } from 'react'

import { uuidSchema } from '../../../lib/validation'

export function SupportHome() {
  const navigate = useNavigate()
  const [reportId, setReportId] = useState('')
  const [invalid, setInvalid] = useState(false)
  function open(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const parsed = uuidSchema.safeParse(reportId.trim().toLowerCase())
    setInvalid(!parsed.success)
    if (parsed.success)
      void navigate({
        to: '/support/reports/$reportId',
        params: { reportId: parsed.data },
      })
  }
  return (
    <>
      <p className="eyebrow">Internal support</p>
      <h1>Saved execution history</h1>
      <p>
        Open a report using its ID. Your support identity determines which
        timelines you can read.
      </p>
      <form onSubmit={open} className="card border-line">
        <label htmlFor="report-id" className="form-label mt-0">
          Report ID
        </label>
        <input
          id="report-id"
          className="form-field"
          value={reportId}
          onChange={(event) => setReportId(event.target.value)}
          aria-invalid={invalid}
          aria-describedby={invalid ? 'report-id-error' : undefined}
          required
        />
        {invalid && (
          <p id="report-id-error" role="alert" className="notice-error">
            Enter a valid report ID.
          </p>
        )}
        <button type="submit" className="button-primary mt-5">
          Open timeline
        </button>
      </form>
    </>
  )
}
