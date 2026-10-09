from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from api.knowledge.metadata import DocumentMetadata, PassageLocation


def metadata(**changes: Any) -> DocumentMetadata:
    values: dict[str, Any] = {
        "document_id": "archived-report",
        "source": "curated_repository",
        "source_path": "knowledge/runbooks/archived-report.md",
        "title": "Archived issue report",
        "document_type": "runbook",
        "service_code": "issue-reports",
        "version": "1",
        "document_date": "2026-10-06",
        "access_class": "INTERNAL",
        "status": "current",
        "fictional": False,
    }
    return DocumentMetadata.model_validate(values | changes)


@pytest.mark.parametrize("access", ["PUBLIC", "INTERNAL", "CUSTOMER_ACCOUNT"])
def test_valid_access_and_json_round_trip(access: str) -> None:
    account = uuid4() if access == "CUSTOMER_ACCOUNT" else None
    source = metadata(access_class=access, customer_account_id=account)
    assert DocumentMetadata.model_validate_json(source.model_dump_json()) == source
    assert source.customer_account_id == account


def test_superseded_source_and_trimmed_identity() -> None:
    source = metadata(
        document_id=" legacy ",
        status="superseded",
        superseded_by=" archived-report ",
        fictional=True,
    )
    assert source.document_id == "legacy"
    assert source.superseded_by == "archived-report"


@pytest.mark.parametrize(
    "changes",
    [
        {"access_class": "CUSTOMER_ACCOUNT"},
        {"access_class": "PUBLIC", "customer_account_id": uuid4()},
        {"access_class": "INTERNAL", "customer_account_id": uuid4()},
        {"access_class": None},
        {"status": "superseded"},
        {"superseded_by": "replacement"},
        {"status": "superseded", "superseded_by": "archived-report"},
        {"title": "  "},
        {"version": ""},
        {"service_code": " "},
        {"document_date": "not-a-date"},
        {"source": "unknown"},
        {"access_class": "unknown"},
        {"document_type": "unknown"},
        {"extra": "ignored?"},
        {"fictional": "false"},
    ],
)
def test_invalid_metadata_is_rejected(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        metadata(**changes)


@pytest.mark.parametrize(
    "path",
    [
        "/etc/passwd",
        "../source.md",
        "knowledge/../source.md",
        "knowledge//source.md",
        "./source.md",
        "C:/source.md",
        "knowledge\\source.md",
        "source.md/",
        "source\x00.md",
    ],
)
def test_source_paths_cannot_escape_relative_posix_contract(path: str) -> None:
    with pytest.raises(ValidationError):
        metadata(source_path=path)


@pytest.mark.parametrize("field", ["access_class", "source", "version", "document_id"])
def test_required_metadata_has_no_default(field: str) -> None:
    values = metadata().model_dump()
    del values[field]
    with pytest.raises(ValidationError):
        DocumentMetadata.model_validate(values)


@pytest.mark.parametrize(
    "location",
    [
        {"kind": "markdown", "heading_path": [], "line_start": 1, "line_end": 1},
        {
            "kind": "markdown",
            "heading_path": ["Checks"],
            "line_start": 10,
            "line_end": 15,
        },
        {"kind": "pdf", "page_number": 2},
    ],
)
def test_passage_keeps_version_and_location_on_round_trip(
    location: dict[str, Any],
) -> None:
    passage = PassageLocation.model_validate(
        {"document_id": "archived-report", "version": "1", "location": location}
    )
    restored = PassageLocation.model_validate_json(passage.model_dump_json())
    assert restored == passage
    assert restored.document_id == "archived-report"
    assert restored.version == "1"


@pytest.mark.parametrize(
    "location",
    [
        {"kind": "markdown", "heading_path": [], "line_start": 5, "line_end": 4},
        {"kind": "markdown", "heading_path": [" "], "line_start": 1, "line_end": 2},
        {"kind": "markdown", "heading_path": [], "line_start": 0, "line_end": 2},
        {"kind": "markdown", "heading_path": [], "line_start": True, "line_end": 2},
        {"kind": "pdf", "page_number": 0},
        {"kind": "pdf", "page_number": "1"},
        {"kind": "pdf", "page_number": 1, "line_start": 1},
        {"kind": "html", "page_number": 1},
    ],
)
def test_invalid_passage_locations_are_rejected(location: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        PassageLocation.model_validate(
            {"document_id": "archived-report", "version": "1", "location": location}
        )


def test_passage_requires_document_and_version() -> None:
    with pytest.raises(ValidationError):
        PassageLocation.model_validate({"location": {"kind": "pdf", "page_number": 1}})


def test_contracts_and_nested_locations_are_frozen() -> None:
    source = metadata()
    with pytest.raises(ValidationError):
        source.version = "2"
    passage = PassageLocation.model_validate(
        {
            "document_id": "archived-report",
            "version": "1",
            "location": {"kind": "pdf", "page_number": 1},
        }
    )
    with pytest.raises(ValidationError):
        passage.location = passage.location
    if passage.location.kind == "pdf":
        with pytest.raises(ValidationError):
            passage.location.page_number = 2
