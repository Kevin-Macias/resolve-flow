import { Link } from '@tanstack/react-router'

export function Brand({ className = '' }: { className?: string }) {
  return (
    <Link to="/" className={`brand ${className}`} aria-label="Resolve Flow">
      <span className="brand-mark" aria-hidden="true">r<span className="text-white/60">f</span></span>
      <span>Resolve<span className="font-normal text-brand">Flow</span></span>
    </Link>
  )
}
