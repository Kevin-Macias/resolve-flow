import { createFileRoute } from '@tanstack/react-router'
import { useEffect, useState } from 'react'

export const Route = createFileRoute('/')({ component: Home })

type ApiState = 'checking' | 'connected' | 'unavailable'

function Home() {
  const [apiState, setApiState] = useState<ApiState>('checking')

  useEffect(() => {
    const apiUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

    fetch(`${apiUrl}/health`)
      .then((response) => {
        if (!response.ok) throw new Error('API health check failed')
        setApiState('connected')
      })
      .catch(() => setApiState('unavailable'))
  }, [])

  return (
    <main>
      <p className="eyebrow">Resolve Flow</p>
      <h1>The workspace is ready.</h1>
      <p className="lede">
        TanStack Start is serving the client and FastAPI is ready for the first
        workflow endpoint.
      </p>
      <div className={`status status--${apiState}`}>
        <span aria-hidden="true" />
        API: {apiState}
      </div>
    </main>
  )
}
