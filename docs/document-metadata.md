# Document metadata (RF-402)

Status: DONE. Kevin approved the contract and completed the final PAIR review.
All 46 metadata tests pass.

## Purpose and scope

Metadata identifies source revisions, enables retrieval filters, and pins
citations to a version and location. Application code controls access policy.
RF-402 supplies framework-independent Pydantic contracts and validation tests;
parsing, ingestion, authorization enforcement, and migrations are separate work.

## Proposed document contract

| Field | Type | Meaning |
| --- | --- | --- |
| `document_id` | Nonempty stable string | Logical source identity retained across revisions, e.g. `archived-report` |
| `source` | Enum: `curated_repository` | Origin of the initial corpus; expand when another origin is needed |
| `source_path` | Relative POSIX path | Repository location, e.g. `knowledge/runbooks/archived-report.md`; no absolute paths or parent traversal |
| `title` | Nonempty string | Human-readable source title |
| `document_type` | Enum: `runbook`, `help_article`, `historical_investigation` | Content purpose, independent of directory |
| `service_code` | Nonempty string | Proposed corpus service label `issue-reports`; does not imply a seeded database Service row |
| `version` | Nonempty string | Source revision label; not limited to integers |
| `document_date` | Date | Authored/revised date of this source version; not an incident date or ingestion timestamp |
| `access_class` | Enum: `PUBLIC`, `INTERNAL`, `CUSTOMER_ACCOUNT` | Existing domain visibility vocabulary |
| `customer_account_id` | UUID or null | Required only for `CUSTOMER_ACCOUNT`; forbidden for other classes |
| `status` | Enum: `current`, `superseded` | Explicit applicability marker; age alone does not establish staleness |
| `superseded_by` | Stable document ID or null | Required for superseded sources; forbidden for current sources; cannot point to self |
| `fictional` | Boolean | Marks invented investigations and legacy behavior; current behavior guides use false |

Account/visibility validation checks structure; retrieval still requires
permission. Access declarations come from trusted source configuration.
Kevin reviews these rules before implementation.

No access class defaults: callers must make the classification explicit.
Reject unknown fields. Strip surrounding whitespace from text fields and reject
empty values. Freeze model instances so consumers cannot casually change a
source binding after validation.

## Proposed source-location contract

Keep document metadata separate from passage location. A document has many
passages; each passage should bind to `document_id` and `version`.

Use a discriminated union with two location types:

- Markdown: `kind="markdown"`, a tuple of nonempty heading names, and inclusive positive
  `line_start`/`line_end`, with end at least start. An empty heading path is
  permitted for text before the first heading.
- PDF: `kind="pdf"` and positive one-based `page_number`.

Locations pin a source version because edits shift lines. PDF locations identify
a page only. RF-403 defines hashing/re-ingestion; chunk identity and citation
formatting come later.

## Example for the current corpus

The archived-report guide would have logical ID `archived-report`, origin
`curated_repository`, path `knowledge/runbooks/archived-report.md`, type `runbook`,
service `issue-reports`, version `1`, document date `2026-10-06`, access `INTERNAL`,
status `current`, and `fictional=false`.

The legacy guide would be `superseded`, refer to `archived-report`, and have
`fictional=true`. Its source revision date is separate from the fictional legacy
date described in its content. A historical investigation can be a current source
describing a resolved past case; resolved is not synonymous with superseded.

## Proposed validation

Test valid current, superseded, public, internal, and account-scoped metadata;
missing and contradictory access declarations; invalid paths; blank fields;
unknown fields; invalid replacement bindings; Markdown ranges and PDF page
numbers; version-bound locations; and serialization round trips. Validate the
eight corpus entries when their authoritative configuration is introduced.

Kevin approved the fields, `issue-reports` service label, access consistency
rules, and location granularity. Models live under `api/knowledge/metadata.py`,
with offline validation tests under `tests/knowledge/test_metadata.py`.

Location validation requires identity/version. RF-403 checks registry bindings,
replacement existence/cycles, files, and resolved path containment. These
contracts check structure; access enforcement belongs to application code.

## Verification

All 46 metadata tests pass. Formatting, lint, and scoped Pyright checks pass for
the new models and tests. Full API Pyright now passes after adding a typed LangGraph boundary and a local
constructor stub; workflow behavior remains unchanged. Tests used the
existing virtual environment directly because uv could not write its default
cache in the sandbox. No runtime endpoints or database tables were changed.

Final verification: full API Pyright, formatting, and lint pass. The Python
suite passed 252 tests; 21 database tests were skipped because no test database
was configured for that run. Async tests were run outside the sandbox after
the first async graph test stalled inside it.
