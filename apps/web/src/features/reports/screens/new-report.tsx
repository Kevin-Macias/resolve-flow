import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from '@tanstack/react-router'
import { useState, type FormEvent } from 'react'

import { reportKeys, reportsApi, type CreateReport } from '../api'
import { ErrorNotice } from '../components/error-notice'
import { ReportIcon } from '../components/report-icon'
import { ServiceInput } from '../components/service-input'
import { useSessionToken, useSessionIsCurrent } from '../session'
import { createReportSchema } from '../validation'

export function NewReport() {
  const token = useSessionToken()
  const isCurrentSession = useSessionIsCurrent()
  const client = useQueryClient()
  const navigate = useNavigate()
  const [description, setDescription] = useState('')
  const [service, setService] = useState('')
  const [validation, setValidation] = useState('')
  const mutation = useMutation({
    mutationFn: (report: CreateReport) => reportsApi(token).create(report),
    onSuccess: async (report) => {
      if (!isCurrentSession()) return
      client.setQueryData(reportKeys.detail(token, report.id), report)
      await client.invalidateQueries({
        queryKey: reportKeys.all(token),
        exact: true,
      })
      if (!isCurrentSession()) return
      await navigate({
        to: '/reports/$reportId',
        params: { reportId: report.id },
      })
    },
  })
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (mutation.isPending) return
    const result = createReportSchema.safeParse({
      description,
      affected_service_code: service,
    })
    if (!result.success) {
      setValidation(result.error.issues[0].message)
      return
    }
    setValidation('')
    mutation.mutate(result.data)
  }
  return (
    <>
      <Link className="reports-back-link" to="/reports">← My reports</Link>
      <div className="reports-page-heading">
        <div>
          <p className="eyebrow">New issue report</p>
          <h1>What happened?</h1>
          <p className="reports-page-description">
            Tell us what you observed so support has the details to work from.
          </p>
        </div>
      </div>
      <div className="new-report-layout">
        <form className="new-report-form" onSubmit={submit}>
          <div className="new-report-form-heading">
            <span className="report-list-icon"><ReportIcon className="size-5" /></span>
            <div><h2>Report details</h2><p>A little context goes a long way.</p></div>
          </div>
          <label className="form-label" htmlFor="description">
            Description
          </label>
          <textarea
            className="form-field report-description-input"
            id="description"
            rows={7}
            maxLength={5000}
            required
            placeholder="I was trying to… but when I…"
            value={description}
            disabled={mutation.isPending}
            onChange={(e) => setDescription(e.target.value)}
          aria-describedby="description-help description-count"
          />
          <div className="description-guidance">
            <p id="description-help">Include when it happened and what you expected.</p>
          <span id="description-count">{description.length.toLocaleString()} / 5,000 characters</span>
          </div>
          <ServiceInput
            value={service}
            onChange={setService}
            disabled={mutation.isPending}
          />
          {validation && (
            <p role="alert" className="notice-error">
              {validation}
            </p>
          )}
          {mutation.isError && (
            <>
              <ErrorNotice error={mutation.error} />
              <p className="hint">
                If the connection failed after submission, check My reports before
                submitting again; the report may have been saved.
              </p>
            </>
          )}
          <p className="hint mt-6 mb-0">Your description stays as submitted. You can update the affected service later.</p>
          <div className="new-report-actions">
            <button
              className="button-primary"
              type="submit"
              disabled={mutation.isPending}
            >
              {mutation.isPending ? 'Submitting…' : 'Submit report'}
            </button>
            <Link className="reports-back-link" to="/reports">Cancel</Link>
          </div>
        </form>
        <aside className="new-report-guide" aria-labelledby="report-guide-title">
          <p className="eyebrow">A helpful starting point</p>
          <h2 id="report-guide-title">The details that help.</h2>
          <ul>
            <li><span>01</span><div><h3>What were you trying to do?</h3><p>Describe the task and what you expected to happen.</p></div></li>
            <li><span>02</span><div><h3>What happened instead?</h3><p>Include any error message and when you first noticed the problem.</p></div></li>
            <li><span>03</span><div><h3>Who is affected?</h3><p>Share what you know about the impact. It’s okay if you’re unsure.</p></div></li>
          </ul>
        </aside>
      </div>
    </>
  )
}
