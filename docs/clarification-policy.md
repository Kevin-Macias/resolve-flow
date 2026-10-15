# Clarification policy (RF-206)

Each validated extraction includes a clarification decision. Gaps are nonempty
`missing_data` or `contradictions`, low interpretation confidence, unknown
service, or unknown severity. Contradictions remain unverified customer claims.

When a gap exists, the policy keeps the first two distinct questions proposed
by the model, preserving their order. Duplicate comparison ignores letter case.
When no gap exists, it returns no questions. If a gap exists but the model
proposes no question, the gap remains visible and no fallback question is
invented. The [RF-304 workflow](workflow-clarification.md) permits at most two
answered rounds and pauses for explicit incomplete continuation if no question
is available or the round limit is reached.

For example, “Payments sometimes remain pending” has unknown impact and can
request the reported affected count. A report that says both “my card was
charged” and “no charge appeared” carries a contradiction and may ask which
statement describes the transaction. A complete, clear report asks nothing.

The application limits and exposes model-proposed questions for workflow
review. Their relevance and the model's interpretation remain unverified.
