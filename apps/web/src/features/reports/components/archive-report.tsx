import { ErrorNotice } from './error-notice'

type ArchiveReportProps = {
  confirmArchive: boolean
  busy: boolean
  editing: boolean
  archiveNeedsRefresh: boolean
  archiving: boolean
  error: unknown | null
  onArchive: () => void
  onCancel: () => void
  onConfirm: () => void
}

export function ArchiveReport({
  confirmArchive,
  busy,
  editing,
  archiveNeedsRefresh,
  archiving,
  error,
  onArchive,
  onCancel,
  onConfirm,
}: ArchiveReportProps) {
  return (
    <section className="card my-5 border-[#e3cec6]">
      <h2>Archive report</h2>
      <p>
        Archiving removes this report from your list. It will no longer be
        available to view or edit. Restore is not available.
      </p>
      {confirmArchive ? (
        <>
          <p id="archive-confirm">Archive this report?</p>
          <div className="form-actions">
            <button
              className="button-danger"
              aria-describedby="archive-confirm"
              disabled={busy || archiveNeedsRefresh}
              onClick={() => {
                if (!busy && !archiveNeedsRefresh) onArchive()
              }}
            >
              {archiving ? 'Archiving…' : 'Confirm archive'}
            </button>
            <button
              className="button-secondary"
              disabled={busy}
              onClick={onCancel}
            >
              Keep report
            </button>
          </div>
        </>
      ) : (
        <button
          className="button-secondary"
          disabled={busy || editing || archiveNeedsRefresh}
          onClick={onConfirm}
        >
          Archive report
        </button>
      )}
      {error !== null && (
        <>
          <ErrorNotice error={error} />
          <p>Refresh the report before attempting another archive.</p>
        </>
      )}
    </section>
  )
}
