"""Classification, clarification, and handled-provider-failure checks."""

import json

from pydantic import TypeAdapter, ValidationError

from api.evaluations.contracts import Case, Values
from api.evaluations.metric_contracts import Checks
from api.extraction.schemas import ExtractionResult
from api.workflow.clarification import ClarificationTurn


def extraction_checks(case: Case, observed: Values, checks: Checks) -> None:
    try:
        extraction = ExtractionResult.model_validate_json(
            json.dumps(observed["extraction"]), strict=True
        )
    except (ValidationError, KeyError):
        checks.record(
            "output_schema",
            "structure",
            "fail",
            False,
            reason="Observed extraction does not satisfy its schema.",
        )
        for name in ("service_allowed", "severity_allowed"):
            checks.record(
                name,
                "service_severity",
                "error",
                reason="No valid extraction available for classification.",
            )
    else:
        checks.record("output_schema", "structure", "pass", True)
        for field, label in (
            ("service_code", "service_allowed"),
            ("severity", "severity_allowed"),
        ):
            value = getattr(extraction, field)
            allowed = case.expected[field + "_allowed"]
            if not isinstance(allowed, list):
                raise ValueError("Invalid approved alternatives")
            valid = value in allowed
            checks.record(label, "service_severity", "pass" if valid else "fail", valid)
    clarification = observed.get("clarification")
    if not isinstance(clarification, dict):
        checks.record(
            "clarification_observation",
            "clarification",
            "error",
            reason="Required clarification observation was not recorded.",
        )
        return
    checks.field(
        "clarification_required",
        "clarification",
        clarification,
        "needs_clarification",
        case.expected["clarification_required"],
    )
    questions = clarification.get("questions")
    bounds = case.expected["question_count"]
    if (
        not isinstance(questions, list)
        or not isinstance(bounds, dict)
        or not all(isinstance(q, str) for q in questions)
    ):
        checks.record(
            "question_count",
            "clarification",
            "error",
            reason="Question count could not be inspected.",
        )
    else:
        limits = TypeAdapter(dict[str, int]).validate_python(bounds)
        valid = limits["min"] <= len(questions) <= limits["max"]
        checks.record(
            "question_count",
            "clarification",
            "pass" if valid else "fail",
            len(questions),
        )
    if "required_reasons" in case.expected:
        reasons = clarification.get("reasons")
        expected = case.expected["required_reasons"]
        if not isinstance(reasons, list) or not isinstance(expected, list):
            checks.record(
                "required_reasons",
                "clarification",
                "error",
                reason="Clarification reasons were not recorded.",
            )
        else:
            valid = all(reason in reasons for reason in expected)
            checks.record(
                "required_reasons", "clarification", "pass" if valid else "fail", valid
            )


def clarification_checks(case: Case, observed: Values, checks: Checks) -> None:
    for key in (
        "provider_calls",
        "terminal_status",
        "incomplete",
        "tool_dispatches",
        "answered_rounds",
    ):
        if key in case.expected:
            dimension = "structure" if key == "tool_dispatches" else "clarification"
            checks.field(key, dimension, observed, key, case.expected[key])
    pauses = observed.get("pauses")
    for key, index in (("pause", 0), ("final_pause", -1)):
        if key not in case.expected:
            continue
        if (
            not isinstance(pauses, list)
            or not pauses
            or not isinstance(pauses[index], dict)
        ):
            checks.record(
                key, "clarification", "error", reason="Saved pause was not recorded."
            )
        else:
            checks.compare(key, "clarification", pauses[index], case.expected[key])
    if "ordered_answers" in case.input:
        turns = observed.get("accepted_turns")
        if not isinstance(turns, list) or not all(
            isinstance(turn, dict) and "answers" in turn for turn in turns
        ):
            checks.record(
                "accepted_answers_in_order",
                "clarification",
                "error",
                reason="Accepted turns were not recorded.",
            )
        else:
            checks.compare(
                "accepted_answers_in_order",
                "clarification",
                [turn["answers"] for turn in turns if isinstance(turn, dict)],
                case.input["ordered_answers"],
            )
    try:
        TypeAdapter(list[ClarificationTurn]).validate_python(observed["accepted_turns"])
        if not isinstance(pauses, list):
            raise ValueError("Missing pauses")
        for pause in pauses:
            if not isinstance(pause, dict) or set(pause) != {
                "mode",
                "cause",
                "questions",
            }:
                raise ValueError("Invalid pause")
            if pause["mode"] not in ("answer_or_continue", "continue_only") or pause[
                "cause"
            ] not in ("questions_available", "no_questions", "round_limit"):
                raise ValueError("Invalid pause state")
            TypeAdapter(list[str]).validate_python(pause["questions"], strict=True)
    except (ValueError, KeyError):
        checks.record("clarification_schema", "structure", "fail", False)
    else:
        checks.record("clarification_schema", "structure", "pass", True)


def failure_checks(case: Case, observed: Values, checks: Checks) -> None:
    for key, expected in case.expected.items():
        checks.field(key, "structure", observed, key, expected)
