import { errorMessage } from '../api'

export function ErrorNotice({ error }: { error: unknown }) {
  return (
    <p className="notice-error" role="alert">
      {errorMessage(error)}
    </p>
  )
}
