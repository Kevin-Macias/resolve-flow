from datetime import datetime
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError

from api.issue_reports.schemas import (
    IssueReportCreate,
    IssueReportResponse,
    IssueReportStatus,
    IssueReportUpdate,
)


def test_issue_report_status() -> None:
    assert IssueReportStatus.DRAFT == "draft"
    assert IssueReportStatus.SUBMITTED == "submitted"
    assert IssueReportStatus.IN_REVIEW == "in_review"
    assert IssueReportStatus.LINKED == "linked"
    assert IssueReportStatus.DELETED == "deleted"
    assert IssueReportStatus.CLOSED == "closed"


def test_create_issue_report_missing_description() -> None:
    with pytest.raises(ValidationError):
        IssueReportCreate()  # type: ignore


def test_create_issue_report_strips_description() -> None:
    report = IssueReportCreate(description="   Payment remains pending     ")
    assert report.description == "Payment remains pending"


def test_create_issue_report_max_description() -> None:
    with pytest.raises(ValidationError):
        IssueReportCreate(description=f"${'a' * 5000}")


def test_create_issue_report_min_description() -> None:
    with pytest.raises(ValidationError):
        IssueReportCreate(description="")


def test_create_issue_report_rejects_blank_description() -> None:
    with pytest.raises(ValidationError):
        IssueReportCreate(description="  ")


def test_create_issue_unexpected_value() -> None:
    with pytest.raises(ValidationError):
        IssueReportCreate.model_validate(
            {
                "description": "This is a good description",
                "bad_field": "sorry, this is a mistake",
            }
        )


def test_customer_update_rejects_status() -> None:
    with pytest.raises(ValidationError):
        IssueReportUpdate.model_validate({"status": IssueReportStatus.CLOSED})


def mock_issue_report_response() -> dict[str, Any]:
    return {
        "id": "596b17e8-0593-43ac-b159-6b59c57e3333",
        "customer_account_id": "39adfa2c-ca2e-4ce2-93ac-e07f92962fa9",
        "description": "Payment remains pending",
        "affected_service": None,
        "status": "submitted",
        "submitted_by": {
            "id": "92f231c1-4c38-45dd-a269-dc48cab09bac",
            "name": "Kevin",
            "last_name": "Macias",
        },
        "created_at": "2026-09-20T12:00:00Z",
        "updated_at": "2026-09-20T12:00:00Z",
    }


@pytest.mark.parametrize(
    "missing_field",
    ["customer_account_id", "submitted_by"],
)
def test_response_reject_missing_field(missing_field: str) -> None:
    valid_response = mock_issue_report_response()
    del valid_response[missing_field]

    with pytest.raises(ValidationError):
        IssueReportResponse.model_validate(valid_response)


def test_response_parses_external_values() -> None:
    response = IssueReportResponse.model_validate(mock_issue_report_response())

    assert isinstance(response.id, UUID)
    assert isinstance(response.customer_account_id, UUID)
    assert isinstance(response.created_at, datetime)
    assert response.status is IssueReportStatus.SUBMITTED
    assert response.submitted_by.name == "Kevin"
