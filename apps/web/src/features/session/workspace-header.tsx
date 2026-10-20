import { Link } from '@tanstack/react-router'

export function WorkspaceHeader({ experience, onSignOut, allowWorkspaceSwitch = true }: {
  experience: 'customer' | 'support'
  onSignOut: () => void
  allowWorkspaceSwitch?: boolean
}) {
  const support = experience === 'support'
  return (
    <header className="workspace-header">
      <Link to="/" className="text-xl font-extrabold no-underline">ResolveFlow</Link>
      <span className="mr-auto text-sm text-muted">
        {support ? 'Support workspace' : 'Customer reports'}
      </span>
      {allowWorkspaceSwitch && <Link to={support ? '/reports' : '/support'}>
        {support ? 'Customer reports' : 'Support timeline'}
      </Link>}
      <button className="button-secondary" onClick={onSignOut}>End session</button>
    </header>
  )
}
