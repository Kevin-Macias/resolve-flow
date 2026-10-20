export function SupportIntroduction() {
  return (
    <>
      <p className="support-console-label">
        <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="4" width="18" height="16" rx="3" />
          <path d="m7 9 3 3-3 3m6 0h4" />
        </svg>
        Support console
      </p>
      <h1 id="sign-in-heading">Your support workspace.</h1>
      <p className="sign-in-description">Review customer reports with the evidence, timeline, and proposed actions in one workspace.</p>
    </>
  )
}

export function SupportCapabilities() {
  return (
    <ul className="support-capabilities" aria-label="Support workspace tools">
        <li>
          <span className="support-capability-icon" aria-hidden="true">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
              <rect x="4" y="3" width="16" height="18" rx="2" /><path d="M8 8h8M8 12h8M8 16h4" />
            </svg>
          </span>
          <div><h2>Review reports</h2><p>Open a report and follow its saved timeline.</p></div>
        </li>
        <li>
          <span className="support-capability-icon" aria-hidden="true">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5M8 10.5h5" />
            </svg>
          </span>
          <div><h2>Inspect evidence</h2><p>Check sources and preliminary findings.</p></div>
        </li>
        <li>
          <span className="support-capability-icon" aria-hidden="true">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
              <path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z" /><path d="m8 12 3 3 5-6" />
            </svg>
          </span>
          <div><h2>Review proposed actions</h2><p>Approve or reject the exact saved proposal.</p></div>
        </li>
    </ul>
  )
}
