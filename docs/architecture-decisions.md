# Architecture decisions

ResolveFlow is a learning project for understanding AI workflows. The stack
provides hands-on experience with typed model outputs, LangGraph pause/resume,
PostgreSQL checkpoints, pgvector retrieval, and evaluations. These choices do
not claim that this stack is the best option for every support system.

The records below explain the application decisions that need context. Each
links to the existing contract so behavior and limitations stay documented in
one place.

## Approval binds to the exact action

Application code controls tool execution. Approval records the saved proposal's
identity, version, and full snapshot fingerprint, because permission to create
one ticket must not authorize changed arguments. Current access is checked again
on resume and execution. This requires a new review when the proposal changes.
See [action approval](action-approval.md) and
[support approval controls](support-approval-controls.md).

## Workflow progress and destination effects have separate records

A checkpoint can remember approval while a destination has already performed
an effect whose reply was lost. Run locks serialize cooperating workers, but
recovery also needs committed application intent and a destination receipt
bound to the same key and proposal. This adds separate commit and recovery
steps. The implemented guarantee covers the local simulated destination; a real
integration needs its own destination idempotency contract. See
[durable simulated execution](tool-idempotency.md).

## Retrieval establishes eligibility before ranking

Trusted application code supplies access scope and active source revisions.
Search applies those restrictions before ranking and limiting results, so
unauthorized sources cannot enter model context or displace eligible evidence.
Citations bind claims to eligible, versioned source passages; similarity alone
does not establish a diagnosis. The cost is explicit metadata, scope, and
citation validation. See [retrieval contracts](retrieval-boundary.md),
[PostgreSQL search integration](retrieval-integration.md), and
[citation validation](citations.md).

## Evaluation results keep their measurement limits

Offline fixtures make regression checks repeatable without provider calls.
Deterministic checks measure observable contracts; semantic assessment has a
separate rubric and provenance. Unmeasured results remain visible, because
passing fixture checks cannot establish live model quality. This requires
separate measurements and reviewed live experiments. See the
[evaluation specification](evaluation-specification.md),
[deterministic metrics](deterministic-metrics.md),
[rubric judging](rubric-judging.md), and
[completed prompt experiment](improvement-experiment.md).

The [architecture](architecture.md) distinguishes implemented components from
the target product flow. In particular, customer confirmation and automatic
retrieval, diagnosis, and proposal orchestration remain separate work.
