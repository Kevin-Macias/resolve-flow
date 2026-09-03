# ResolveFlow agent instructions

These instructions apply to the entire repository and to every new Codex
session started from this project.

## Start of every task

Before proposing or changing project work, read:

1. `docs/roadmap.md`
2. `docs/working-agreement.md`
3. `docs/product.md`
4. `docs/architecture.md` when the task affects system design

Treat those files as the shared source of truth. Inspect the current code and
Git status before assuming that a documented ticket is implemented. Preserve
unrelated user changes.

## When Kevin asks "What's next?"

1. Find the single ticket marked `NEXT` in `docs/roadmap.md`.
2. Report its ID, title, ownership label, goal, acceptance criteria, and relevant
   dependencies.
3. Explain the immediate learning objective in a few sentences.
4. Follow the ticket's ownership mode described below.
5. Do not start implementation merely because Kevin asked what is next. Wait
   until he asks to begin or provides his attempt.

If no ticket is marked `NEXT`, inspect completed work and dependencies, then
recommend one ticket. Do not edit its status until Kevin agrees. If multiple
tickets are marked `NEXT`, point out the inconsistency and recommend which one
should remain next.

## Ownership modes

### HAND

Kevin writes the first design and implementation. Codex may:

- Explain concepts and relevant Python or AI engineering principles
- Point to primary documentation
- Ask guiding questions
- Review pseudocode, code, tests, and tradeoffs
- Give small isolated examples or hints
- Diagnose errors in Kevin's attempt

Codex must not provide or apply the first complete implementation of a HAND
ticket. If Kevin explicitly asks Codex to take over, confirm that this changes
the ticket to `PAIR` or `DELEGATE`, update the roadmap after agreement, and then
proceed under the new mode.

### PAIR

Kevin owns behavior, acceptance criteria, and architectural decisions. Codex
may suggest approaches and implement agreed framework-specific or repetitive
parts. Surface consequential choices instead of silently deciding them. Kevin
must review the result and personally verify important edge cases.

### DELEGATE

Codex may implement the scoped ticket after confirming its contract from the
roadmap and codebase. Include appropriate tests, run relevant checks, preserve
unrelated work, and summarize the resulting diff for Kevin to review.

## Ticket lifecycle

- Keep exactly one ticket marked `NEXT` unless work is intentionally blocked.
- Change a ticket to `DONE` only after its acceptance criteria and relevant
  automated checks have been verified.
- When a ticket is completed, update `docs/roadmap.md` in the same change and
  promote the next dependency-safe ticket to `NEXT`.
- Use `BLOCKED` only with a concise reason and identify what would unblock it.
- Do not mark existing boilerplate as completion of a learning ticket when that
  ticket explicitly requires Kevin to perform or explain the work.
- If implementation changes scope or architecture, update `docs/product.md` or
  `docs/architecture.md` as appropriate.

## Definition of done

A ticket is complete only when:

- Its documented acceptance criteria are satisfied.
- Relevant tests, lint checks, and type checks pass, or an environmental blocker
  is recorded clearly.
- Important failure paths and edge cases are covered.
- User-visible and architectural documentation is current.
- Kevin can explain HAND and PAIR work at interview depth.

## Project commands

Use the Node version in `.nvmrc`. From an interactive shell, run `nvm use`
before pnpm commands.

Common root commands:

```bash
pnpm install
pnpm setup
pnpm dev
pnpm check
pnpm docker:up
pnpm docker:down
```

The repository may contain uncommitted work. Never discard or overwrite it to
complete a ticket.
