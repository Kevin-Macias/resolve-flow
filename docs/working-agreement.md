# Learning and AI working agreement

ResolveFlow is a product and a learning project: moving from full-stack
JavaScript into AI engineering. Understanding and explaining the Python, LLM,
retrieval, workflow, evaluation, and safety decisions comes before speed.

## Ownership labels

### HAND

Kevin owns the first design and implementation. AI may teach concepts, answer
questions, provide small examples, review code, identify edge cases, and give
hints. It should not supply the first complete implementation.

Workflow:

1. Read the relevant primary documentation.
2. Write pseudocode or a short design note.
3. Implement the first version.
4. Ask AI for review.
5. Apply and understand the corrections.
6. Record the lesson or tradeoff when it matters later.

### PAIR

Kevin defines behavior and acceptance criteria. AI may propose approaches and
help implement framework-specific or repetitive pieces. Kevin chooses the
design, tests edge cases, and must be able to explain the final code.

### DELEGATE

AI may implement the ticket from an agreed contract. It must preserve existing
work, include appropriate tests, and report its changes. Kevin reviews the diff,
runs the checks, and does not accept code he cannot explain.

## Work that remains human-owned

Even when implementation is paired, Kevin owns decisions about:

- Product scope and domain language
- Severity and clarification policy
- Workflow state and transition semantics
- Approval, authorization, and tool safety
- Retrieval relevance and citation correctness
- Evaluation cases, expected behavior, and metric interpretation
- Architecture tradeoffs and portfolio claims

## Testing progression

For RF-101, Kevin writes the first schema tests by hand to learn pytest test
discovery, assertions, exception checks, and Pydantic runtime validation.

After RF-101, AI may write routine unit and integration tests for `HAND`
tickets. Kevin defines or approves important behaviors and edge cases, reviews
the tests, and checks that they catch incorrect behavior. He still owns
evaluation expectations, safety policy, access boundaries, and adversarial cases.

## AI implementation rules

Before AI starts a ticket, the request should identify:

- Ticket ID and intended outcome
- Acceptance criteria
- Files or system boundaries in scope
- Tests that demonstrate completion
- Whether the mode is HAND, PAIR, or DELEGATE

AI should inspect the repository and current roadmap status before changing
code. It should not mark a ticket `DONE` until its acceptance criteria have been
verified. A delegated ticket that reveals a new architectural decision returns
to Kevin for that decision instead of silently expanding scope.

## Frontend styling

Define shared styles as general classes in `apps/web/src/styles.css`, using
Tailwind `@apply` inside `@layer components`. Use names such as `button-primary`
directly in JSX. Add Tailwind utilities on individual elements for small
adjustments; the utilities layer overrides shared component styles. Global CSS
also holds theme tokens and base typography/focus rules. Keep Tailwind class
names complete so the build can discover them.

## Frontend validation

Use shared Zod schemas for frontend forms and runtime API/stream payload
validation. Submit parsed form values to the typed API client and validate
responses before caching or displaying them. Keep protocol ordering and
connection-state checks explicit. Backend Pydantic models remain the authority
for accepted data and access rules.

## Definition of done

A ticket is done when:

- Its acceptance criteria are satisfied.
- Relevant tests, type checks, and lint checks pass.
- Errors and important edge cases are covered.
- Documentation reflects externally visible or architectural changes.
- The roadmap status is updated.
- Kevin can explain the result at the depth expected in an interview.
