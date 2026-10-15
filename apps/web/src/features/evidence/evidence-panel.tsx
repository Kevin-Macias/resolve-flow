import { useSupportEvidence } from './use-support-evidence'

export function EvidencePanel({
  reportId,
  onAccessLost,
}: {
  reportId: string
  onAccessLost: () => void
}) {
  const {
    query,
    saved,
    mutation,
    needsRefresh,
    busy,
    disabled,
    analyze,
    refresh,
    error,
  } = useSupportEvidence({ reportId, onAccessLost })
  return (
    <section
      className="card mt-8 border-line"
      aria-labelledby="evidence-heading"
    >
      <h2 id="evidence-heading">Evidence</h2>
      <p className="hint">
        Preliminary support analysis of unconfirmed customer observations.
        Review each claim against its sources.
      </p>
      {query.isPending && <p role="status">Loading saved evidence…</p>}
      {error && (
        <p role="alert" className="notice-error">
          {error}
        </p>
      )}
      {saved && query.isError && (
        <p className="notice">
          Showing stale saved evidence. Refresh before starting another
          analysis.
        </p>
      )}
      {needsRefresh && (
        <p className="notice">
          The last analysis may have been accepted. Refresh saved evidence
          before continuing.
        </p>
      )}
      {saved?.status === 'absent' && (
        <p>No evidence analysis has been requested for this report.</p>
      )}
      {saved && saved.status !== 'absent' && (
        <>
          <p className="notice">
            {saved.simulated
              ? 'Offline simulation — fixture ranking and scripted analysis.'
              : 'Live provider analysis — requires human review.'}
          </p>
          <p className="hint">
            Saved: {saved.created_at} · Intake revision:{' '}
            {saved.input_revision ?? 'No intake run'}
          </p>
          {saved.older_input && (
            <p className="notice">
              This analysis uses older observations. Start a new analysis to
              review the current input.
            </p>
          )}
        </>
      )}
      {saved?.status === 'pending' && (
        <p role="status">
          An analysis is pending or was interrupted. Refresh to check its saved
          outcome. Recovery requires support review; another analysis is
          blocked.
        </p>
      )}
      {saved?.status === 'failed' && (
        <p role="status">
          The analysis failed. No evidence was published. You can explicitly
          request a new analysis.
        </p>
      )}
      {saved?.status === 'ready' && (
        <>
          {!saved.passages.length && (
            <p>
              No eligible passages were returned. This does not establish that
              evidence does not exist.
            </p>
          )}
          {saved.report.claims.map((claim) => (
            <article key={claim.draft.claim_id} className="mt-5">
              <h3>
                {
                  {
                    supported: 'Supported',
                    inference: 'Inference',
                    missing_evidence: 'Missing evidence',
                    conflict: 'Conflict',
                  }[claim.draft.kind]
                }
              </h3>
              <p>{claim.draft.statement}</p>
              {claim.draft.explanation && <p>{claim.draft.explanation}</p>}
              {claim.citations.map((ref) => (
                <p key={`${ref.citation.chunk_id}:${ref.role}`}>
                  {ref.role === 'supports' ? 'Supports' : 'Contradicts'}:{' '}
                  {ref.citation.metadata.title}
                </p>
              ))}
            </article>
          ))}
          <p className="hint">
            Scores describe retrieval similarity, not confidence in a diagnosis.
            Fixture scores do not measure semantic relevance.
          </p>
          {saved.passages.map((item) => {
            const citation = item.citation
            const location = citation.passage.location
            return (
              <article key={citation.citation_id} className="mt-5">
                <h3>{citation.metadata.title}</h3>
                <p className="hint break-all">
                  {citation.metadata.source_path} ·{' '}
                  {citation.metadata.document_id}@{citation.metadata.version}
                </p>
                <p>
                  {location.kind === 'markdown'
                    ? `${location.heading_path.join(' > ') || 'Preamble'}, lines ${location.line_start}–${location.line_end}`
                    : `Page ${location.page_number}`}
                </p>
                <p>
                  Rank {item.rank} ·{' '}
                  {item.score_metric === 'fixture'
                    ? 'Fixture score'
                    : 'Cosine similarity'}
                  : {item.score.toFixed(3)}
                </p>
                {citation.metadata.fictional && (
                  <p className="notice">
                    Fictional investigation — cannot prove this report's state.
                  </p>
                )}
                {item.historical && (
                  <p className="notice">
                    Historical source revision — review current guidance before
                    acting.
                  </p>
                )}
                <pre className="whitespace-pre-wrap break-words font-sans">
                  {citation.excerpt}
                </pre>
              </article>
            )
          })}
        </>
      )}
      <div className="mt-5 flex flex-wrap gap-3">
        <button
          className="button-primary"
          disabled={disabled}
          onClick={analyze}
        >
          {mutation.isPending ? 'Analyzing…' : 'Analyze evidence'}
        </button>
        <button
          className="button-secondary"
          disabled={busy}
          onClick={() => void refresh()}
        >
          {query.isFetching ? 'Refreshing evidence…' : 'Refresh saved evidence'}
        </button>
      </div>
    </section>
  )
}
