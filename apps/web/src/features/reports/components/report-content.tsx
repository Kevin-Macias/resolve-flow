import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { useState } from 'react'

import { reportKeys, reportsApi, type IssueReport } from '../api'
import { useSessionToken, useSessionIsCurrent } from '../session'
import { updateReportSchema } from '../validation'
import { ArchiveReport } from './archive-report'
import { ReportStatus } from './report-status'
import { ReportSummary } from './report-summary'
import { ServiceEditor } from './service-editor'

export function ReportContent({
  report,
  refreshing,
  refresh,
}: {
  report: IssueReport
  refreshing: boolean
  refresh: () => Promise<boolean>
}) {
  const token = useSessionToken()
  const client = useQueryClient()
  const navigate = useNavigate()
  const isCurrentSession = useSessionIsCurrent()
  const [editing, setEditing] = useState(false)
  const [service, setService] = useState(report.affected_service?.code ?? '')
  const [confirmArchive, setConfirmArchive] = useState(false)
  const [archiveNeedsRefresh, setArchiveNeedsRefresh] = useState(false)
  const [notice, setNotice] = useState('')
  const update = useMutation({
    mutationFn: () =>
      reportsApi(token).update(
        report.id,
        updateReportSchema.parse({ affected_service_code: service }),
      ),
    onSuccess: async (updated) => {
      if (!isCurrentSession()) return
      client.setQueryData(reportKeys.detail(token, report.id), updated)
      setEditing(false)
      setNotice('Affected service updated.')
      await client.invalidateQueries({
        queryKey: reportKeys.all(token),
        exact: true,
      })
    },
  })
  const archive = useMutation({
    mutationFn: () => reportsApi(token).archive(report.id),
    onError: () => setArchiveNeedsRefresh(true),
    onSuccess: async () => {
      if (!isCurrentSession()) return
      client.removeQueries({
        queryKey: reportKeys.detail(token, report.id),
        exact: true,
      })
      await client.invalidateQueries({
        queryKey: reportKeys.all(token),
        exact: true,
      })
      if (!isCurrentSession()) return
      await navigate({ to: '/reports' })
    },
  })
  const busy = update.isPending || archive.isPending || refreshing
  async function refreshReport() {
    if (await refresh()) {
      archive.reset()
      update.reset()
      setArchiveNeedsRefresh(false)
      setNotice('Report refreshed.')
    }
  }
  return (
    <>
      <div className="flex items-center justify-between gap-4 max-[600px]:flex-col max-[600px]:items-start [&_p]:mt-0">
        <div>
          <p className="eyebrow">Issue report</p>
          <h1>Your report</h1>
        </div>
        <ReportStatus report={report} />
      </div>
      <p className="hint wrap-anywhere">Report ID: {report.id}</p>
      {notice && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}
      <ReportSummary report={report} />
      <ServiceEditor
        editing={editing}
        service={service}
        busy={busy}
        confirmArchive={confirmArchive}
        saving={update.isPending}
        error={update.isError ? update.error : null}
        onServiceChange={setService}
        onSave={() => update.mutate()}
        onCancel={() => {
          setEditing(false)
          update.reset()
        }}
        onEdit={() => {
          setService(report.affected_service?.code ?? '')
          setEditing(true)
          setNotice('')
        }}
      />
      <ArchiveReport
        confirmArchive={confirmArchive}
        busy={busy}
        editing={editing}
        archiveNeedsRefresh={archiveNeedsRefresh}
        archiving={archive.isPending}
        error={archive.isError ? archive.error : null}
        onArchive={() => archive.mutate()}
        onCancel={() => setConfirmArchive(false)}
        onConfirm={() => {
          setConfirmArchive(true)
          setNotice('')
        }}
      />
      <button
        className="button-secondary"
        disabled={busy}
        onClick={() => void refreshReport()}
      >
        {refreshing ? 'Refreshing…' : 'Refresh report'}
      </button>
    </>
  )
}
