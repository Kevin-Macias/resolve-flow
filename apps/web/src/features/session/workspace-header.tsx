import { Link } from '@tanstack/react-router'

import { Brand } from '../../components/brand'

export function WorkspaceHeader({ experience, onSignOut, allowWorkspaceSwitch = true }: {
  experience: 'customer' | 'support'
  onSignOut: () => void
  allowWorkspaceSwitch?: boolean
}) {
  const support = experience === 'support'
  return (
    <header className="workspace-header">
      <Brand className="workspace-brand" />
      <div className="workspace-header-actions">
        {allowWorkspaceSwitch && <Link className="workspace-switch-link" to={support ? '/reports' : '/support'}>
          {support ? 'Customer reports' : 'Support timeline'}
        </Link>}
        <button className="logout-button" type="button" onClick={onSignOut}>
          <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
            <path d="M9 5H5v14h4M14 8l4 4-4 4M9 12h9" />
          </svg>
          Log out
        </button>
      </div>
    </header>
  )
}
