"""Typed workflow with bounded clarification and checkpointed transition events."""

from collections.abc import Awaitable, Callable
from typing import Literal
from uuid import UUID

from langgraph.checkpoint.base import (  # pyright: ignore[reportMissingTypeStubs]
    BaseCheckpointSaver,
)
from langgraph.checkpoint.memory import (  # pyright: ignore[reportMissingTypeStubs]
    InMemorySaver,
)
from langgraph.graph import (  # pyright: ignore[reportMissingTypeStubs]
    END,
    START,
    StateGraph,
)
from langgraph.graph.state import (  # pyright: ignore[reportMissingTypeStubs]
    CompiledStateGraph,
)
from langgraph.types import interrupt  # pyright: ignore[reportMissingTypeStubs]

from api.extraction.clarification import decide_clarification
from api.extraction.provider import LLMProvider
from api.extraction.service import (
    DEFAULT_RETRY_POLICY,
    ExtractionError,
    RetryPolicy,
    extract_issue_report,
)
from api.workflow.checkpoints import checkpoint_serializer
from api.workflow.clarification import (
    ClarificationTurn,
    extraction_input,
    prepare_clarification,
    validate_reply,
)
from api.workflow.state import (
    CustomerSafeReport,
    DiagnosisDraft,
    ReportStatus,
    SafeWorkflowFailure,
    WorkflowInput,
    WorkflowState,
    WorkflowUpdate,
)
from api.workflow.timeline import EventMetadata, EventType, transition_event

type ReportLoader = Callable[[UUID], Awaitable[str]]


def build_workflow(
    load_report: ReportLoader,
    provider: LLMProvider,
    retry_policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    *,
    checkpointer: BaseCheckpointSaver[str] | None = None,
) -> CompiledStateGraph[WorkflowState, None, WorkflowInput, WorkflowState]:
    """Use a trusted loader that checks current access before returning text.

    The returned state is internal. Expose only customer_update to customers;
    graph streams and the other state fields are not public responses.
    """

    def event(
        state: WorkflowState,
        kind: EventType,
        metadata: EventMetadata | None = None,
        *,
        key: str | None = None,
    ) -> WorkflowUpdate:
        return {
            "timeline": transition_event(
                state["workflow_run_id"],
                state.get("timeline", []),
                "intake",
                kind,
                key
                if key is not None
                else str(len(state.get("clarification_turns", []))),
                metadata,
            )
        }

    def start(state: WorkflowState) -> WorkflowUpdate:
        return event(state, EventType.WORKFLOW_STARTED, key="start")

    async def classify(state: WorkflowState) -> WorkflowUpdate:
        report = await load_report(state["issue_report_id"])
        report = extraction_input(report, state.get("clarification_turns", ()))
        try:
            outcome = await extract_issue_report(report, provider, retry_policy)
        except ExtractionError as error:
            return {
                **event(
                    state,
                    EventType.EXTRACTION_FAILED,
                    EventMetadata(
                        attempts=error.call.attempts,
                        extraction_failure=error.reason,
                        provider_failure=error.provider_failure_kind,
                    ),
                ),
                "extraction_call": error.call,
                "failure": SafeWorkflowFailure(
                    "classify", error.reason, error.provider_failure_kind
                ),
            }
        return {
            **event(
                state,
                EventType.EXTRACTION_SUCCEEDED,
                EventMetadata(attempts=outcome.call.attempts),
            ),
            "extraction": outcome.result,
            "extraction_call": outcome.call,
        }

    def after_classify(state: WorkflowState) -> Literal["evaluate", "report"]:
        return "report" if "failure" in state else "evaluate"

    def evaluate(state: WorkflowState) -> WorkflowUpdate:
        extraction = state.get("extraction")
        assert extraction is not None
        decision = decide_clarification(extraction)
        return {
            **event(
                state,
                EventType.CLARIFICATION_EVALUATED,
                EventMetadata(reasons=decision.reasons),
            ),
            "clarification": decision,
        }

    def after_evaluate(state: WorkflowState) -> Literal["prepare", "diagnose"]:
        decision = state.get("clarification")
        assert decision is not None
        return "prepare" if decision.needs_clarification else "diagnose"

    def prepare(state: WorkflowState) -> WorkflowUpdate:
        decision = state.get("clarification")
        assert decision is not None
        pending = prepare_clarification(
            decision, len(state.get("clarification_turns", ()))
        )
        return {
            **event(
                state,
                EventType.CLARIFICATION_REQUESTED,
                EventMetadata(
                    round_number=pending.round_number,
                    reasons=pending.reasons,
                    question_count=len(pending.questions),
                    clarification_cause=pending.cause,
                ),
                key=str(pending.pending_id),
            ),
            "pending_clarification": pending,
            "customer_update": CustomerSafeReport(
                ReportStatus.NEEDS_CLARIFICATION,
                "Answer the questions or choose to continue with incomplete information."
                if pending.questions
                else "More context is needed. Choose whether to continue with incomplete information.",
                pending.questions,
            ),
        }

    async def clarify(state: WorkflowState) -> WorkflowUpdate:
        # This node re-enters on resume. Recheck access, but never call the model
        # or append answers before interrupt returns a validated reply.
        await load_report(state["issue_report_id"])
        pending = state.get("pending_clarification")
        assert pending is not None
        payload = pending.model_dump(mode="json")
        while True:
            raw: object = interrupt(payload)
            reply = validate_reply(raw, pending)
            if reply is not None:
                break
            payload = {**pending.model_dump(mode="json"), "error": "invalid_reply"}
        if reply.action == "continue_incomplete":
            return {
                **event(
                    state,
                    EventType.CONTINUED_INCOMPLETE,
                    EventMetadata(incomplete=True),
                    key=str(pending.pending_id),
                ),
                "continued_incomplete": True,
                "pending_clarification": None,
            }
        assert pending.round_number is not None
        turn = ClarificationTurn(
            round_number=pending.round_number,
            questions=pending.questions,
            answers=reply.answers,
        )
        return {
            **event(
                state,
                EventType.CLARIFICATION_ANSWERED,
                EventMetadata(round_number=turn.round_number),
                key=str(pending.pending_id),
            ),
            "clarification_turns": [*state.get("clarification_turns", []), turn],
            "pending_clarification": None,
        }

    def after_clarify(state: WorkflowState) -> Literal["diagnose", "classify"]:
        return "diagnose" if state.get("continued_incomplete", False) else "classify"

    def diagnose(state: WorkflowState) -> WorkflowUpdate:
        extraction = state.get("extraction")
        assert extraction is not None
        return {
            **event(
                state,
                EventType.DIAGNOSIS_PREPARED,
                EventMetadata(incomplete=state.get("continued_incomplete", False)),
            ),
            "diagnosis": DiagnosisDraft(
                reported_facts=tuple(extraction.reported_facts),
                missing_data=tuple(extraction.missing_data),
                contradictions=tuple(extraction.contradictions),
            ),
        }

    def report(state: WorkflowState) -> WorkflowUpdate:
        if "failure" in state:
            update = CustomerSafeReport(
                ReportStatus.EXTRACTION_FAILED,
                "We could not process your report. It needs review before retrying.",
            )
        elif state.get("continued_incomplete", False):
            update = CustomerSafeReport(
                ReportStatus.NEEDS_CONFIRMATION,
                "Your report is ready for confirmation with unresolved information.",
                incomplete=True,
            )
        else:
            update = CustomerSafeReport(
                ReportStatus.NEEDS_CONFIRMATION,
                "Your structured report is ready for your confirmation.",
            )
        return {
            **event(
                state,
                EventType.REPORT_READY,
                EventMetadata(incomplete=update.incomplete),
            ),
            "customer_update": update,
        }

    # LangGraph ships partial typing here. Keep suppressions at its API calls;
    # application state, nodes, and updates remain checked in strict mode.
    builder = StateGraph(WorkflowState, input_schema=WorkflowInput)
    builder.add_node("start", start)
    builder.add_node("classify", classify)
    builder.add_node("evaluate", evaluate)
    builder.add_node("diagnose", diagnose)
    builder.add_node("report", report)
    builder.add_node("prepare", prepare)
    builder.add_node("clarify", clarify)
    builder.add_edge(START, "start")
    builder.add_edge("start", "classify")
    builder.add_conditional_edges("classify", after_classify)
    builder.add_conditional_edges("evaluate", after_evaluate)
    builder.add_edge("prepare", "clarify")
    builder.add_conditional_edges("clarify", after_clarify)
    builder.add_edge("diagnose", "report")
    builder.add_edge("report", END)
    saver = (
        checkpointer
        if checkpointer is not None
        else InMemorySaver(serde=checkpoint_serializer())
    )
    return builder.compile(checkpointer=saver)
