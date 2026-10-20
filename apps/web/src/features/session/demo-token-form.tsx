import { useState, type FormEvent } from 'react'

import { demoTokenSchema } from '../reports/validation'

export function DemoTokenForm({ experience, onConnect }: {
  experience: 'customer' | 'support'
  onConnect: (token: string) => void
}) {
  const [token, setToken] = useState('')
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const result = demoTokenSchema.safeParse(token)
    if (result.success) onConnect(result.data)
  }
  return (
    <form onSubmit={submit}>
      <label className="form-label" htmlFor="demo-token">Demo {experience} token</label>
      <input className="form-field" id="demo-token" type="password" autoComplete="off"
        value={token} onChange={(event) => setToken(event.target.value)} required />
      <p className="hint">
        Use a configured demo {experience} identity. Your token stays in memory until
        you end the session or reload this page.
      </p>
      <button className="button-primary" type="submit">
        {experience === 'support' ? 'Open support timeline' : 'Open my reports'}
      </button>
    </form>
  )
}
