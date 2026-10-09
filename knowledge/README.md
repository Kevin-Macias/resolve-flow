# ResolveFlow troubleshooting corpus

RF-401 completed: issue-report submission and visibility. Kevin approved the
scope and completed the PAIR review of the source documents.

Current guides describe existing API behavior. Historical investigations and
legacy behavior are explicitly fictional. No new operational feature is implied.
The [manifest](manifest.json) supplies validated authoritative source metadata.
Visibility is explicit; retrieval authorization enforcement belongs to later tickets. No private customer records are included.

| Document | Intended visibility | Role |
| --- | --- | --- |
| [Submission validation](runbooks/submission-validation.md) | INTERNAL | Rejected creation |
| [Archived report](runbooks/archived-report.md) | INTERNAL | Disappearance after creation |
| [Account visibility](runbooks/account-visibility.md) | INTERNAL | Account-scoped access |
| [Legacy visibility](runbooks/legacy-visibility.md) | INTERNAL | Explicitly superseded fictional advice |
| [Affected-service update](runbooks/affected-service-update.md) | INTERNAL | Plausible irrelevant source |
| [Resolved investigation](sample-incidents/resolved-archived-report.md) | INTERNAL | Fictional verified explanation |
| [Unresolved investigation](sample-incidents/unresolved-submission.md) | INTERNAL | Fictional ambiguity |
| [Customer help](runbooks/missing-report-help.md) | PUBLIC | Customer-safe guidance |

Review alongside the [feature summary](../docs/issue-report-troubleshooting.md)
and [dataset plan](../docs/knowledge-dataset.md). A guide supports general behavior;
case-specific evidence is still needed to confirm a customer's cause.

RF-403 reads only the eight manifest-listed documents. See the
[ingestion contract](../docs/markdown-ingestion.md) for revisions, hashes, and
usage. RF-405 adds an async PostgreSQL adapter for durable revisions; the memory store
remains available for offline tests. See [vector storage](../docs/vector-storage.md)
for migration and ingestion commands.
