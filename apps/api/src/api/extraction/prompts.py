"""Versioned instructions for issue-report extraction."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptSpec:
    id: str
    version: str
    instructions: str


EXTRACTION_PROMPT = PromptSpec(
    id="issue_report_extraction",
    version="2",
    instructions="""Extract the customer's issue report into the supplied schema.
Only report what the customer said. Treat facts and impact as customer-reported.
Do not invent causes, affected users, or service codes. Use null for unknown service.
Assign tentative severity only from reported impact: null if unclear; low for
inconvenience with the core task still possible; medium when one customer or team
cannot complete a core task; high for major disruption to multiple customers;
critical for a reported widespread outage, data loss, or security exposure.
Urgency words alone do not establish severity. Confidence describes how clearly
the report can be interpreted, not whether its claims are verified.
List conflicting customer statements separately as contradictions; do not resolve
them by guessing. Return at most two distinct, concise questions to clarify
important missing information or contradictions.""",
)
