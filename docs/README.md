# ResolveFlow project documentation

These files are the shared source of truth for planning and implementation.
They are intentionally stored beside the code so that decisions and progress
change in the same commits as the application.

Repository-level behavior for new Codex sessions is defined in
[`AGENTS.md`](../AGENTS.md). It tells a fresh session how to answer "What's
next?" and how to respect each ticket's ownership mode.

## Documents

| Document | Purpose | Update when |
| --- | --- | --- |
| [Product brief](product.md) | Defines the problem, users, scope, and demo | Product behavior or scope changes |
| [Architecture](architecture.md) | Describes what exists and where the design is going | Components, boundaries, or data flow change |
| [Domain language](domain-language.md) | Defines shared product terms and visibility boundaries | A domain concept or relationship changes |
| [Extraction contract](extraction-contract.md) | Defines validated issue-report extraction output | Extraction fields or semantics change |
| [Severity policy](severity-policy.md) | Defines tentative severity rules and examples | Impact classification rules change |
| [Clarification policy](clarification-policy.md) | Defines when to ask and how many questions to keep | Clarification triggers or limits change |
| [Prompt and model settings](prompt-and-model-settings.md) | Records extraction prompt version and model settings | Prompt text or model configuration changes |
| [Retry policy](retry-policy.md) | Defines provider timeouts, retryable failures, and attempt limits | Extraction failure handling changes |
| [Deterministic AI tests](deterministic-ai-tests.md) | Lists offline extraction scenarios and their limits | Test expectations change |
| [Live model check](live-model-check.md) | Explains the opt-in extraction check and its output | Live command or metrics change |
| [Provider boundary](provider-boundary.md) | Defines the OpenAI and fake model adapters | Provider behavior or interface changes |
| [Roadmap](roadmap.md) | Tracks tickets, phases, ownership, and status | Work starts, finishes, or is reprioritized |
| [Working agreement](working-agreement.md) | Defines which work is for learning and which may be delegated | Collaboration rules change |

## Progress update checklist

When completing a ticket:

1. Verify its acceptance criteria and automated checks.
2. Change its status in `roadmap.md`.
3. Update `architecture.md` if the implemented design differs from it.
4. Record important tradeoffs in the ticket, commit, or a future architecture
   decision record.
5. Select only one new `NEXT` ticket so that the immediate learning objective
   remains clear.

The roadmap records product progress, but Git remains the source of truth for
the exact implementation history.
