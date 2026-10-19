"""Execute actual extraction and intake graph behavior with literal fixtures."""

import asyncio
from dataclasses import asdict
from typing import cast
from uuid import NAMESPACE_URL, uuid5

from langgraph.types import Command
from pydantic import BaseModel, TypeAdapter

from api.evaluations.contracts import Case, CaseSet, Values, observations
from api.extraction.provider import ModelSettings, ProviderResult
from api.extraction.schemas import ExtractionResult
from api.extraction.service import ExtractionError, RetryPolicy, extract_issue_report
from api.workflow.checkpoints import workflow_config
from api.workflow.graph import build_workflow
from api.workflow.state import WorkflowState


class FixtureProvider:
    settings = ModelSettings(model="evaluation-fixture-v1")

    def __init__(self, responses: list[ProviderResult], *, timeout: bool = False):
        self.responses = responses
        self.timeout = timeout
        self.calls = 0

    async def generate(
        self,
        instructions: str,
        input_text: str,
        output_schema: type[BaseModel] | None = None,
    ) -> ProviderResult:
        self.calls += 1
        if self.timeout:
            await asyncio.Event().wait()
        if self.calls > len(self.responses):
            raise ValueError("Fixture response sequence exhausted")
        return self.responses[self.calls - 1]


def provider_for(case: Case, data: CaseSet) -> FixtureProvider:
    if "provider_response_fixture" in case.setup:
        names = [case.setup["provider_response_fixture"]]
    else:
        names = case.setup.get("provider_response_sequence", [])
    responses: list[ProviderResult] = []
    if not isinstance(names, list):
        raise ValueError("Invalid fixture sequence")
    for name in names:
        if not isinstance(name, str):
            raise ValueError("Invalid fixture name")
        payload = ExtractionResult.model_validate(data.provider_response_fixtures[name])
        responses.append(ProviderResult(text=payload.model_dump_json()))
    if "provider_result" in case.setup:
        raw = case.setup["provider_result"]
        if not isinstance(raw, dict):
            raise ValueError("Invalid fixture result")
        responses = [TypeAdapter(ProviderResult).validate_python(raw)]
    return FixtureProvider(
        responses,
        timeout=case.setup.get("provider_behavior") == "wait_until_attempt_cancelled",
    )


async def execute_extraction(case: Case, data: CaseSet) -> Values:
    provider = provider_for(case, data)
    report = case.input["report"]
    if not isinstance(report, str):
        raise ValueError("Missing report")
    retry = TypeAdapter(RetryPolicy).validate_python(case.setup.get("retry_policy", {}))
    try:
        outcome = await extract_issue_report(report, provider, retry)
    except ExtractionError as error:
        return observations(
            dict(
                extraction_failure=error.reason.value,
                provider_failure=error.provider_failure_kind.value
                if error.provider_failure_kind
                else None,
                attempts=error.call.attempts,
                provider_calls=provider.calls,
                valid_extraction=False,
                classification_status="not_applicable",
                error_text_contains_raw_exception=False,
                call=asdict(error.call),
            )
        )
    return observations(
        dict(
            extraction=outcome.result.model_dump(mode="json"),
            clarification={
                "reasons": list(outcome.clarification.reasons),
                "questions": list(outcome.clarification.questions),
                "needs_clarification": outcome.clarification.needs_clarification,
            },
            provider_calls=provider.calls,
            call=asdict(outcome.call),
        )
    )


async def execute_clarification(case: Case, data: CaseSet) -> Values:
    provider = provider_for(case, data)

    async def load_report(_report_id: object) -> str:
        return str(case.input["report"])

    graph = build_workflow(load_report, provider)
    run_id = uuid5(NAMESPACE_URL, case.case_id + ":intake")
    config = workflow_config(run_id)
    steps = case.setup["steps"]
    if not isinstance(steps, list):
        raise ValueError("Invalid scenario steps")
    pauses: list[object] = []
    state: WorkflowState
    for step in steps:
        if not isinstance(step, dict):
            raise ValueError("Invalid step")
        if step["operation"] == "start_intake":
            await graph.ainvoke(
                {"workflow_run_id": run_id, "issue_report_id": uuid5(run_id, "report")},
                config,
            )
        else:
            state = cast(WorkflowState, (await graph.aget_state(config)).values)
            pending = state.get("pending_clarification")
            if pending is None:
                raise ValueError("Expected saved pause")
            if step["operation"] == "answer_current_questions":
                answers = case.input["ordered_answers"]
                index = step["answers_index"]
                if not isinstance(answers, list) or not isinstance(index, int):
                    raise ValueError("Invalid answers")
                reply = dict(
                    pending_id=str(pending.pending_id),
                    action="answer",
                    answers=answers[index],
                )
            elif step["operation"] == "continue_incomplete":
                reply = dict(
                    pending_id=str(pending.pending_id),
                    action="continue_incomplete",
                    answers=step["answers"],
                )
            else:
                raise ValueError("Unsupported clarification step")
            await graph.ainvoke(Command(resume=reply), config)
        state = cast(WorkflowState, (await graph.aget_state(config)).values)
        pending = state.get("pending_clarification")
        if pending:
            pauses.append(
                dict(
                    mode=pending.mode,
                    cause=pending.cause,
                    questions=list(pending.questions),
                )
            )
    state = cast(WorkflowState, (await graph.aget_state(config)).values)
    update = state.get("customer_update")
    return observations(
        dict(
            pauses=pauses,
            answered_rounds=len(state.get("clarification_turns", [])),
            accepted_turns=[
                turn.model_dump(mode="json")
                for turn in state.get("clarification_turns", [])
            ],
            provider_calls=provider.calls,
            terminal_status=update.status.value if update else None,
            incomplete=state.get("continued_incomplete", False),
            tool_dispatches=0,
        )
    )
