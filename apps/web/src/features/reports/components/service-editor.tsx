import { ErrorNotice } from './error-notice'
import { ServiceInput } from './service-input'

type ServiceEditorProps = {
  editing: boolean
  service: string
  busy: boolean
  confirmArchive: boolean
  saving: boolean
  error: unknown | null
  onServiceChange: (value: string) => void
  onSave: () => void
  onCancel: () => void
  onEdit: () => void
}

export function ServiceEditor({
  editing,
  service,
  busy,
  confirmArchive,
  saving,
  error,
  onServiceChange,
  onSave,
  onCancel,
  onEdit,
}: ServiceEditorProps) {
  return (
    <section className="card my-5 border-line">
      <h2>Affected service</h2>
      <p>
        The original description and report status cannot be changed here.
      </p>
      {editing ? (
        <form
          onSubmit={(e) => {
            e.preventDefault()
            if (!busy) onSave()
          }}
        >
          <ServiceInput
            value={service}
            onChange={onServiceChange}
            disabled={busy}
          />
          {error !== null && <ErrorNotice error={error} />}
          <div className="form-actions">
            <button
              className="button-primary"
              type="submit"
              disabled={busy}
            >
              {saving ? 'Saving…' : 'Save service'}
            </button>
            <button
              className="button-secondary"
              type="button"
              disabled={busy}
              onClick={onCancel}
            >
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <button
          className="button-secondary"
          disabled={busy || confirmArchive}
          onClick={onEdit}
        >
          Edit service
        </button>
      )}
    </section>
  )
}
