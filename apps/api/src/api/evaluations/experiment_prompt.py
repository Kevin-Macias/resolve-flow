"""RF-607 prompt pair approved before observing live experiment outputs."""

from api.evaluations.experiment_contracts import PromptSnapshot, Variant
from api.evaluations.judge_prompt import digest
from api.extraction.prompts import EXTRACTION_PROMPT, PromptSpec

BASELINE_SHA256 = "37e4d3c21600e816c530a24126a2067c7048d83490affc82d7bf24344a9a79bd"
CANDIDATE_SHA256 = "657aa4602ba8160424629ffc41ce7ea4d5e59c4ad9159e7071e5b2964c4d543c"
ADDITION = """Preserve material reported details in the summary and reported facts, including
unaffected customers and the availability or absence of a workaround. Keep
conflicting observations without choosing an unverified explanation. Attribute
security-exposure allegations to the customer and flag prompt human review,
without implying that verification or escalation has occurred. Ask questions
only about unresolved gaps or contradictions; do not ask for information already
supplied or introduce an unsupported cause or outage as a premise."""
CASE_IDS = (
    "RF602-S01",
    "RF602-S02",
    "RF602-M01",
    "RF602-M02",
    "RF602-M03",
    "RF602-A01",
)
VARIANTS: tuple[Variant, ...] = ("baseline", "candidate")


def prompts() -> dict[Variant, PromptSpec]:
    if (
        EXTRACTION_PROMPT.version != "3"
        or digest(EXTRACTION_PROMPT.instructions) != BASELINE_SHA256
    ):
        raise ValueError("Baseline prompt changed from the approved experiment")
    candidate = PromptSpec(
        EXTRACTION_PROMPT.id,
        "3-rf607-candidate-1",
        EXTRACTION_PROMPT.instructions + "\n\n" + ADDITION,
    )
    if digest(candidate.instructions) != CANDIDATE_SHA256:
        raise ValueError("Candidate prompt changed from the approved experiment")
    return {"baseline": EXTRACTION_PROMPT, "candidate": candidate}


def snapshot(prompt: PromptSpec) -> PromptSnapshot:
    return PromptSnapshot(
        id=prompt.id,
        version=prompt.version,
        instructions=prompt.instructions,
        sha256=digest(prompt.instructions),
    )
