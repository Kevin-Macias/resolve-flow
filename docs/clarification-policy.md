# Clarification policy (RF-206)

Each validated extraction now includes a decision that explains whether more
context is needed. The decision identifies these gaps: nonempty `missing_data`,
nonempty `contradictions`, low interpretation confidence, unknown service, or
unknown severity. Contradictions remain reported conflicts, not verified facts.

When a gap exists, the policy keeps the first two distinct questions proposed
by the model, preserving their order. Duplicate comparison ignores letter case.
When no gap exists, it returns no questions. If a gap exists but the model
proposes no question, the gap remains visible and no fallback question is
invented. The later workflow decides how to proceed in that case and how many
clarification rounds to allow.

For example, “Payments sometimes remain pending” has unknown impact and can
request the reported affected count. A report that says both “my card was
charged” and “no charge appeared” carries a contradiction and may ask which
statement describes the transaction. A complete, clear report asks nothing.

The application does not verify the model's interpretation of the report or
judge whether a proposed question is semantically relevant. It bounds and
exposes the proposed questions for later workflow review.
