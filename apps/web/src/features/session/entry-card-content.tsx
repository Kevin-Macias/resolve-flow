import type { ReactNode } from 'react'

export function EntryCardContent({ icon, title, description }: {
  icon: 'invitation' | 'workspace'
  title: string
  description: string
}) {
  const paths: Record<typeof icon, ReactNode> = {
    invitation: <><rect x="4" y="5" width="16" height="14" rx="2" /><path d="M8 10h8M8 14h4" /></>,
    workspace: <><rect x="3" y="7" width="18" height="14" rx="2" /><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 12h18M10 12v3h4v-3" /></>,
  }
  return (
    <>
      <span className="entry-card-icon" aria-hidden="true">
        <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">{paths[icon]}</svg>
      </span>
      <span className="min-w-0 flex-1">
        <span className="block font-semibold">{title}</span>
        <span className="mt-1 block text-sm opacity-75">{description}</span>
      </span>
      <span className="text-xl" aria-hidden="true">→</span>
    </>
  )
}
