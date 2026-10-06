# Durable workflow checkpoints (RF-305)

PostgreSQL can now restore the same workflow after its Python process exits.
Kevin approved LangGraph's async PostgreSQL saver, a separate `workflow` schema,
explicit setup, and a real process-restart test.
Kevin approved the implementation and restart behavior in the RF-305 PAIR review.

## Setup

Start the local database and add the host-side URL to your root `.env`:

```dotenv
DATABASE_URL=postgresql://resolve_flow:resolve_flow_local@localhost:5432/resolve_flow
```

From the repository root, with the Node version in `.nvmrc` selected:

```bash
pnpm setup:checkpoints
```

This explicitly creates `workflow` and runs `AsyncPostgresSaver.setup()`. The
library owns its checkpoint tables and records its migration versions in
`workflow.checkpoint_migrations`; application tables remain owned by Alembic.
Setup can be repeated. It is not called during API startup or graph invocation.
Run it again after updating the checkpointer dependency if its migrations change.

The local `workflow` schema was initialized during RF-305 verification. The
setup script reports success or a safe configuration error without printing
the connection URL. Runtime credentials need checkpoint read/write access;
setup credentials additionally need schema/table/index creation permissions.

## Connection lifetime and resume

```python
from langgraph.types import Command
from api.workflow.checkpoints import open_checkpointer, workflow_config
from api.workflow.graph import build_workflow

config = workflow_config(workflow_run_id)
async with open_checkpointer(database_url) as saver:
    graph = build_workflow(load_report, provider, checkpointer=saver)
    state = await graph.ainvoke({
        "workflow_run_id": workflow_run_id,
        "issue_report_id": issue_report_id,
    }, config, durability="sync")
```

After restarting, open a new saver connection and build a new graph with the same
run UUID. Inspect the checkpoint to recover the pending questions, then resume:

```python
async with open_checkpointer(database_url) as saver:
    graph = build_workflow(load_report, provider, checkpointer=saver)
    snapshot = await graph.aget_state(config)
    pending = snapshot.values["pending_clarification"]
    state = await graph.ainvoke(Command(resume={
        "pending_id": str(pending.pending_id),
        "action": "continue_incomplete",
    }), config, durability="sync")
```

Use `Command(resume=...)` with the same thread ID; submitting the original input
again starts graph execution from its entry point. Keep the saver context open
for all graph operations; leaving it closes the connection. The runtime uses
autocommit, dictionary rows, and disabled prepared statements as required by
the PostgreSQL saver. `durability="sync"` requests checkpoint writes before
execution advances. See the official
[PostgreSQL memory example](https://docs.langchain.com/oss/python/langgraph/add-memory).

`build_workflow` still defaults to an in-memory saver when none is injected, so
ordinary offline tests require no database. Durable storage is explicit, with
no silent fallback if PostgreSQL or setup is unavailable. No API endpoint or
application startup wiring is added in this ticket.

## Stored data and types

Checkpoints include report/run IDs, validated extraction, prompt/model metadata,
pending questions and their ID, ordered clarification turns, safe failures,
preliminary diagnosis, customer-safe updates, and the RF-310 typed
[execution timeline](execution-timeline.md). They omit the original report
text and provider/connection/access-context objects. Extracted facts and answers
can still contain sensitive customer information: checkpoint tables are internal
storage, not a customer response or audit log.

The serializer permits exact application model, enum, and dataclass symbols plus
LangGraph's built-in safe types. Pickle fallback is disabled. Typed snapshots are
restored without replacing their Python contracts with untyped dictionaries.
MessagePack arrays decode as lists; immutable tuple fields in dataclasses are
normalized on construction, while clarification history is an ordered list.

Existing checkpoint compatibility depends on stable type names and fields. A
future incompatible state change requires an explicit migration or versioned
reader before old runs are resumed; this ticket does not implement arbitrary
schema upgrades. Raw model output, report text, and live keys are not used in
the restart test.

## Boundaries

- A thread ID selects stored state; it does not authorize access. Future request
  integration must bind actor, run, report, and thread before reads or resume.
  The trusted report loader still checks current access when clarification resumes.
- Checkpoint durability preserves completed drafts and pending steps. A crash
  during an unfinished model node may require repeating that unfinished call.
  It does not guarantee exactly-once tool effects; RF-309/703 own that boundary.
- Checkpointer writes use their own connection and commits. They are not part
  of a SQLAlchemy issue-report transaction.
- Timeline events now live in checkpoint state (RF-310). Checkpoint retention,
  authentication, and full application workflow-run records remain separate work.

## Verification

`tests/workflow/test_checkpoints.py` checks restored application values/types,
schema and URL validation, repeatable setup, and missing-schema failure. Its
restart test launches four separate Python processes: pause, answer and pause
again, continue incomplete, then inspect the completed run. It checks stable
run/report IDs, preserved answers and call metadata, typed restored drafts,
and no model calls while polling or continuing a saved pause.

Database tests use a unique schema with real committed checkpoint writes. A
`finally` cleanup drops that test schema and verifies its removal. Set
`TEST_DATABASE_URL` to run them; ordinary test runs skip these integration cases
when the variable is absent. They never require a live model.

Verification on 2026-09-26: local setup completed; `pnpm check` passed formatting,
lint, generated client drift checks, all type checks, and all 146 tests with
PostgreSQL available, including the separate-process restart test.
