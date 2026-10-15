import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from '@tanstack/react-router'
import { useState, type FormEvent } from 'react'

import { reportKeys, reportsApi, type CreateReport } from '../api'
import { ErrorNotice } from '../components/error-notice'
import { ServiceInput } from '../components/service-input'
import { useDemoToken, useSessionIsCurrent } from '../session'
import { createReportSchema } from '../validation'

export function NewReport() {
  const token = useDemoToken()
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
      <Link to="/reports">← My reports</Link>
      <p className="eyebrow">New issue report</p>
      <h1>What happened?</h1>
      <p>
        Share what you observed. You can change the affected service later; the
        original description stays as submitted.
      </p>
      <form className="card my-5 border-line" onSubmit={submit}>
        <label className="form-label" htmlFor="description">
          Description
        </label>
        <textarea
          className="form-field resize-y leading-relaxed"
          id="description"
          rows={7}
          maxLength={5000}
          required
          value={description}
          disabled={mutation.isPending}
          onChange={(e) => setDescription(e.target.value)}
          aria-describedby="description-help"
        />
        <p id="description-help" className="hint">
          {description.length.toLocaleString()} / 5,000 characters. Include when
          it happened and what you expected.
        </p>
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
        <div className="form-actions">
          <button
            className="button-primary"
            type="submit"
            disabled={mutation.isPending}
          >
            {mutation.isPending ? 'Submitting…' : 'Submit report'}
          </button>
          <Link to="/reports">Cancel</Link>
        </div>
      </form>
    </>
  )
}
