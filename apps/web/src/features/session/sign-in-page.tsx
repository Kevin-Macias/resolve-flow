import { Link } from '@tanstack/react-router'
import type { ReactNode } from 'react'

import { AccountForm } from './account-form'
import { DemoTokenForm } from './demo-token-form'
import { EntryCardContent } from './entry-card-content'
import { SupportCapabilities, SupportIntroduction } from './support-introduction'

type SignInProps = {
  authMode: 'demo' | 'password'
  onConnect: (token: string, role?: 'customer' | 'support') => void
  notice: string
}

function SignInLayout({ introduction, children, workspaceLink, details, appearance = 'customer' }: {
  introduction: ReactNode
  children: ReactNode
  workspaceLink: ReactNode
  details?: ReactNode
  appearance?: 'customer' | 'support'
}) {
  return (
    <main className={appearance === 'support' ? 'sign-in-page support-sign-in' : 'sign-in-page'}>
      <section className={details ? 'sign-in-hero sign-in-hero-with-details' : 'sign-in-hero'} aria-labelledby="sign-in-heading">
        <div className="sign-in-introduction">
          <Link to="/" className="sign-in-brand" aria-label="Resolve Flow">
            <span className="brand-mark" aria-hidden="true">r<span className="text-white/60">f</span></span>
            <span>Resolve<span className="font-normal text-brand">Flow</span></span>
          </Link>
          {introduction}
        </div>
        <div className="sign-in-card-stack">
          {children}
          {workspaceLink}
          <p className="hint sign-in-session-note">Your session stays in memory. Reloading signs you out on this browser.</p>
        </div>
        {details && <div className="sign-in-details">{details}</div>}
      </section>
    </main>
  )
}

function SignInForm({ experience, authMode, onConnect, notice }: SignInProps & {
  experience: 'customer' | 'support'
}) {
  return (
    <>
      {notice && <p role="status" className="notice relative z-10">{notice}</p>}
      {authMode === 'password'
        ? <AccountForm experience={experience} onConnect={onConnect} />
        : <div className="card sign-in-card">
          {experience === 'support' && <p className="access-label">Internal access</p>}
          <DemoTokenForm experience={experience} onConnect={onConnect} />
        </div>}
    </>
  )
}

export function CustomerSignIn(props: SignInProps) {
  return (
    <SignInLayout introduction={<>
      <p className="eyebrow">My reports</p>
      <h1 id="sign-in-heading">Keep support in the loop.</h1>
      <p className="sign-in-description">Submit a problem, review your reports, and update the affected service.</p>
    </>} workspaceLink={<WorkspaceSwitchCard experience="customer" />}>
      <SignInForm experience="customer" {...props} />
    </SignInLayout>
  )
}

export function SupportSignIn(props: SignInProps) {
  return (
    <SignInLayout appearance="support" introduction={<SupportIntroduction />} details={<SupportCapabilities />}
      workspaceLink={<Link to="/reports" className="sign-in-return">Customer reports <span aria-hidden="true">→</span></Link>}>
      <SignInForm experience="support" {...props} />
    </SignInLayout>
  )
}

function WorkspaceSwitchCard({ experience }: { experience: 'customer' | 'support' }) {
  const support = experience === 'support'
  return (
    <Link className="entry-card workspace-switch-card" to={support ? '/reports' : '/support'}>
      <EntryCardContent icon="workspace" title={support ? 'Looking for customer reports?' : 'Working in support?'}
        description={support ? 'Open your customer reports' : 'Open the support workspace'} />
    </Link>
  )
}
