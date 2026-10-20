import { useEffect, useRef, useState, type FormEvent } from 'react'

import { accountApi, enrollmentSchema, loginSchema } from './account-api'
import { EntryCardContent } from './entry-card-content'

export function AccountForm({ experience, onConnect }: {
  experience: 'customer' | 'support'
  onConnect: (token: string, role: 'customer' | 'support') => void
}) {
  const invitationEmail = import.meta.env.VITE_INVITATION_EMAIL?.trim()
  const [enrolling, setEnrolling] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const mounted = useRef(true)
  const inFlight = useRef(false)
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (inFlight.current) return
    const fields = Object.fromEntries(new FormData(event.currentTarget))
    const parsed = enrolling ? enrollmentSchema.safeParse(fields) : loginSchema.safeParse(fields)
    if (!parsed.success) { setError(parsed.error.issues[0]?.message ?? 'Check your details.'); return }
    inFlight.current = true
    setBusy(true)
    setError('')
    try {
      const session = enrolling
        ? await accountApi.enroll(enrollmentSchema.parse(fields))
        : await accountApi.login(loginSchema.parse(fields))
      if (!mounted.current) {
        void accountApi.logout(session.access_token).catch(() => undefined)
        return
      }
      onConnect(session.access_token, session.user.user_type)
    } catch (error) {
      if (mounted.current) setError(error instanceof TypeError
        ? enrolling ? 'Could not confirm account setup. Try signing in with your invited email and password.' : 'Could not reach ResolveFlow. Try signing in again.'
        : error instanceof Error ? error.message : 'Sign-in could not be completed.')
    } finally {
      inFlight.current = false
      if (mounted.current) setBusy(false)
    }
  }
  return <>
    <div className="card sign-in-card">
    {experience === 'support' && <p className="access-label">Internal access</p>}
    <h2 className="sign-in-title">{enrolling ? 'Accept your invitation' : 'Sign in'}</h2>
    <p className="sign-in-subtitle">{enrolling ? 'Set up your account to get started.' : experience === 'support' ? 'Welcome back to your support workspace.' : 'Welcome back. Let’s get you connected.'}</p>
    {error && <p role="alert" className="notice-error">{error}</p>}
    <form onSubmit={(event) => void submit(event)} key={enrolling ? 'enroll' : 'login'}>
      {enrolling ? <>
        <label className="form-label" htmlFor="invitation">Invitation token</label>
        <input className="form-field" id="invitation" name="token" type="password" autoComplete="off" maxLength={256} required disabled={busy} />
        <label className="form-label" htmlFor="first-name">First name</label>
        <input className="form-field" id="first-name" name="name" autoComplete="given-name" maxLength={200} required disabled={busy} />
        <label className="form-label" htmlFor="last-name">Last name</label>
        <input className="form-field" id="last-name" name="last_name" autoComplete="family-name" maxLength={200} required disabled={busy} />
      </> : <>
        <label className="form-label" htmlFor="email">Email</label>
        <input className="form-field" id="email" name="email" type="email" autoComplete="username" required disabled={busy} />
      </>}
      <label className="form-label" htmlFor="password">Password</label>
      <input className="form-field" id="password" name="password" type="password" autoComplete={enrolling ? 'new-password' : 'current-password'} minLength={enrolling ? 15 : 1} maxLength={128} required disabled={busy} />
      {enrolling && <p className="hint">Use at least 15 characters. Your invitation fixes your email and account access. You can sign in again after setup.</p>}
      <button className="button-primary mt-5 w-full" type="submit" disabled={busy}>{busy ? 'Connecting…' : enrolling ? 'Create account' : 'Sign in'}</button>
    </form>
    {invitationEmail && <p className="hint mb-0 text-center">
      Need access? <a href={`mailto:${encodeURIComponent(invitationEmail)}?subject=${encodeURIComponent('ResolveFlow invitation request')}`}>Request an invitation</a>
    </p>}
    </div>
    <button className="entry-card invitation-card" type="button" disabled={busy}
      aria-label={enrolling ? 'Already accepted? Sign in' : 'Have an invitation?'}
      onClick={() => { setEnrolling(!enrolling); setError('') }}>
      <EntryCardContent icon="invitation" title={enrolling ? 'Already accepted? Sign in' : 'Have an invitation?'}
        description={enrolling ? 'Return to your account.' : 'Use your invitation to set up your account.'} />
    </button>
  </>
}
