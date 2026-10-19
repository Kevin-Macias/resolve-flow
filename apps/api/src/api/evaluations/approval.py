"""Observe the real support API and durable approval stage, including cancellation."""

import asyncio
from contextlib import suppress
from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient, Response

from api.evaluations.contracts import Case, Values, observations
from api.evaluations.database import EvaluationDatabase
from api.main import create_app
from api.support.action_schemas import ProposalRequest, SupportAction
from api.support.actions import SupportActions
from api.workflow.actions import CreateTicketArguments
from api.workflow.execution import SimulatedCreateTicketTool, SimulatedTicketResult


class ObservedTool(SimulatedCreateTicketTool):
    def __init__(self, behavior: str, exception_text: str):
        super().__init__()
        self.behavior = behavior
        self.exception_text = exception_text
        self.entered = asyncio.Event()

    async def create_ticket(
        self, arguments: CreateTicketArguments, idempotency_key: UUID
    ) -> SimulatedTicketResult:
        result = await super().create_ticket(arguments, idempotency_key)
        self.entered.set()
        if self.behavior == "record_dispatch_then_raise":
            raise RuntimeError(self.exception_text)
        if self.behavior == "pause_on_entry_before_return":
            await asyncio.Event().wait()
        return result


async def execute_approval(case: Case, database: EvaluationDatabase) -> Values:
    report_id = await database.report(
        "Customer reports that a submitted issue report is missing. The cause is unverified."
    )
    await database.completed_intake(report_id)
    tool = ObservedTool(
        str(case.setup["tool_behavior"]),
        str(case.setup.get("exception_text", "private fixture exception")),
    )

    def service() -> SupportActions:
        result = SupportActions(
            database.sessions, database.url, database.checkpoint_schema
        )
        result.tool = lambda: tool
        return result

    app = create_app()
    app.state.session_factory = database.sessions
    app.state.support_actions = service()
    path = f"/support/issue-reports/{report_id}"
    aliases: dict[str, SupportAction] = {}
    saved: SupportAction | None = None
    response_states: list[SupportAction] = []
    statuses: list[int] = []
    first_dispatches: int | None = None
    steps = case.setup["steps"]
    if not isinstance(steps, list):
        raise ValueError("Invalid approval steps")
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://evaluation",
        headers={"Authorization": "Bearer evaluation-support"},
    ) as client:
        for step in steps:
            if not isinstance(step, dict):
                raise ValueError("Invalid approval step")
            operation = step["operation"]
            if operation in ("prepare", "revise"):
                fields = case.input["proposal_fields"]
                if not isinstance(fields, dict):
                    raise ValueError("Invalid proposal fields")
                body = dict(fields)
                previous = aliases[str(step["from"])] if operation == "revise" else None
                if previous:
                    body["title"] = case.input["revised_title"]
                draft = ProposalRequest.model_validate(
                    body
                    | {
                        "operation_id": uuid4(),
                        "expected_fingerprint": previous.fingerprint
                        if previous
                        else None,
                    }
                )
                response = await client.post(
                    f"{path}/proposal", json=draft.model_dump(mode="json")
                )
                response.raise_for_status()
                saved = SupportAction.model_validate_json(response.text)
                aliases[str(step["save_as"])] = saved
            elif operation in (
                "decide",
                "approve_and_interrupt_after_durable_receipt_before_result",
            ):
                original = aliases[str(step["proposal"])]
                if original.proposal is None:
                    raise ValueError("Missing saved proposal")
                body = dict(
                    action_id=str(original.proposal.action_id),
                    version=original.proposal.version,
                    fingerprint=original.fingerprint,
                    decision=step.get("decision", "approve"),
                )

                async def submit(
                    run_id: UUID | None = original.run_id,
                    reply: Values = body,
                ) -> Response:
                    return await client.post(
                        f"{path}/runs/{run_id}/decision", json=reply
                    )

                if (
                    operation
                    == "approve_and_interrupt_after_durable_receipt_before_result"
                ):
                    task = asyncio.create_task(submit())
                    try:
                        await asyncio.wait_for(tool.entered.wait(), timeout=10)
                    finally:
                        task.cancel()
                        with suppress(asyncio.CancelledError):
                            await task
                    first_dispatches = len(tool.calls)
                    # The cancelled request has no response to interpret.
                    continue
                response = await submit()
                if first_dispatches is None:
                    first_dispatches = len(tool.calls)
                statuses.append(response.status_code)
                if response.status_code == 200:
                    saved = SupportAction.model_validate_json(response.text)
                    response_states.append(saved)
                elif response.status_code != 409:
                    response.raise_for_status()
            elif operation == "recreate_reader_and_runner":
                app.state.support_actions = service()
            elif operation == "read_action":
                response = await client.get(f"{path}/action")
                response.raise_for_status()
                saved = SupportAction.model_validate_json(response.text)
                response_states.append(saved)
            else:
                raise ValueError("Unsupported approval step")
        response = await client.get(f"{path}/action")
        response.raise_for_status()
        saved = SupportAction.model_validate_json(response.text)
    serialized = saved.model_dump_json()
    decision_matches = bool(
        saved.decision
        and saved.proposal
        and saved.decision.action_id == saved.proposal.action_id
        and saved.decision.version == saved.proposal.version
        and saved.decision.fingerprint == saved.fingerprint
    )
    first = aliases.get("v1")
    binding_matches = bool(
        saved.proposal
        and first
        and first.proposal
        and saved.proposal.action_id == first.proposal.action_id
        and saved.proposal.arguments.issue_report_id == report_id
    )
    return observations(
        dict(
            report_id=str(report_id),
            final_proposal=saved.proposal.model_dump(mode="json")
            if saved.proposal
            else None,
            decision_receipt=saved.decision.model_dump(mode="json")
            if saved.decision
            else None,
            proposal_snapshots={
                name: item.proposal.model_dump(mode="json") if item.proposal else None
                for name, item in aliases.items()
            },
            outcomes=[
                dict(
                    decision=item.decision.model_dump(mode="json")
                    if item.decision
                    else None,
                    execution=item.execution.model_dump(mode="json")
                    if item.execution
                    else None,
                    failure=item.failure.model_dump(mode="json")
                    if item.failure
                    else None,
                )
                for item in response_states
            ],
            saved_decision=saved.decision.decision.value if saved.decision else None,
            execution_status=saved.status,
            simulated_success=saved.execution is not None,
            tool_dispatches=len(tool.calls),
            decision_request_statuses=statuses,
            current_version=saved.proposal.version if saved.proposal else None,
            proposal_identity_preserved=binding_matches,
            decision_binding_valid=decision_matches if saved.decision else None,
            retry_dispatches=len(tool.calls) - (first_dispatches or 0),
            same_saved_outcome=len(response_states) >= 2
            and all(item == response_states[0] for item in response_states),
            saved_result=saved.execution.model_dump(mode="json")
            if saved.execution
            else None,
            error_text_contains_raw_exception=tool.exception_text in serialized,
        )
    )
