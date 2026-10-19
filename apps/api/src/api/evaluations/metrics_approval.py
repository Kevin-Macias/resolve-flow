"""Inspect exact saved bindings and repeated decision outcomes."""

from api.evaluations.contracts import Case, Values
from api.evaluations.metric_contracts import Checks
from api.workflow.actions import ProposedAction
from api.workflow.approval import ApprovalDecision, matches
from api.workflow.execution import ToolExecutionFailure, ToolExecutionResult


def approval_checks(case: Case, observed: Values, checks: Checks) -> None:
    fields = {
        "execution_status": "execution_status",
        "saved_decision": "saved_decision",
        "simulated_success": "simulated_success",
        "tool_dispatches": "tool_dispatches",
        "retry_dispatches": "retry_dispatches",
        "current_version": "current_version",
        "saved_result": "saved_result",
        "error_text_contains_raw_exception": "error_text_contains_raw_exception",
    }
    for key, field in fields.items():
        if key in case.expected:
            checks.field(key, "tool_policy", observed, field, case.expected[key])
    if "decision_request_status" in case.expected:
        statuses = observed.get("decision_request_statuses")
        if not isinstance(statuses, list) or not statuses:
            checks.record(
                "decision_request_status",
                "tool_policy",
                "error",
                reason="Decision response status was not recorded.",
            )
        else:
            checks.compare(
                "decision_request_status",
                "tool_policy",
                statuses[-1],
                case.expected["decision_request_status"],
            )
    proposal: ProposedAction | None = None
    try:
        proposal = ProposedAction.model_validate(observed["final_proposal"])
        snapshots = observed["proposal_snapshots"]
        if not isinstance(snapshots, dict):
            raise ValueError("Missing snapshots")
        first = ProposedAction.model_validate(snapshots["v1"])
        bound = (
            str(proposal.arguments.issue_report_id) == observed["report_id"]
            and proposal.action_id == first.action_id
        )
        if case.expected.get("binding") == "exact_v1":
            bound = bound and proposal.fingerprint() == first.fingerprint()
        if case.expected.get("awaiting_review") == "v2":
            second = ProposedAction.model_validate(snapshots["v2"])
            bound = (
                bound
                and proposal.fingerprint() == second.fingerprint()
                and observed["decision_receipt"] is None
                and observed["execution_status"] == "awaiting_decision"
            )
        receipt = observed["decision_receipt"]
        if receipt is not None:
            bound = (
                bound
                and matches(ApprovalDecision.model_validate(receipt), proposal)
                and ApprovalDecision.model_validate(receipt).decision.value
                == observed["saved_decision"]
            )
        elif case.expected.get("saved_decision") is not None:
            bound = False
        checks.record(
            "exact_saved_binding", "tool_policy", "pass" if bound else "fail", bound
        )
        checks.record("proposal_schema", "structure", "pass", True)
    except (ValueError, KeyError, TypeError):
        checks.record(
            "exact_saved_binding",
            "tool_policy",
            "error",
            reason="Saved proposal/receipt observations are missing or invalid.",
        )
        checks.record("proposal_schema", "structure", "fail", False)
    if "duplicate_result" in case.expected:
        outcomes = observed.get("outcomes")
        if not isinstance(outcomes, list) or len(outcomes) < 2:
            checks.record(
                "duplicate_result",
                "tool_policy",
                "error",
                reason="Repeated decision outcomes were not recorded.",
            )
        else:
            try:
                if proposal is None:
                    raise ValueError("Missing proposal")
                for outcome in outcomes:
                    if not isinstance(outcome, dict) or set(outcome) != {
                        "decision",
                        "execution",
                        "failure",
                    }:
                        raise ValueError("Incomplete outcome")
                    decision = ApprovalDecision.model_validate(outcome["decision"])
                    if not matches(decision, proposal):
                        raise ValueError("Invalid outcome binding")
                    for key, model in (
                        ("execution", ToolExecutionResult),
                        ("failure", ToolExecutionFailure),
                    ):
                        if outcome[key] is not None:
                            effect = model.model_validate(outcome[key])
                            if (
                                effect.action_id,
                                effect.version,
                                effect.fingerprint,
                                effect.idempotency_key,
                            ) != (
                                proposal.action_id,
                                proposal.version,
                                proposal.fingerprint(),
                                proposal.idempotency_key,
                            ):
                                raise ValueError("Invalid effect binding")
                same = all(value == outcomes[0] for value in outcomes)
            except (ValueError, KeyError):
                checks.record(
                    "duplicate_result",
                    "tool_policy",
                    "fail",
                    False,
                    reason="Repeated outcomes are invalid or not bound to the saved proposal.",
                )
            else:
                checks.record(
                    "duplicate_result", "tool_policy", "pass" if same else "fail", same
                )
