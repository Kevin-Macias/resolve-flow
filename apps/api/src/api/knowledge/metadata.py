"""Validated source descriptions and version-bound passage locations."""

from datetime import date
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

type Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
type PositiveInt = Annotated[int, Field(strict=True, ge=1)]


class KnowledgeContract(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, revalidate_instances="always"
    )


class DocumentType(StrEnum):
    RUNBOOK = "runbook"
    HELP_ARTICLE = "help_article"
    HISTORICAL_INVESTIGATION = "historical_investigation"


class AccessClass(StrEnum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CUSTOMER_ACCOUNT = "CUSTOMER_ACCOUNT"


class DocumentStatus(StrEnum):
    CURRENT = "current"
    SUPERSEDED = "superseded"


class DocumentMetadata(KnowledgeContract):
    document_id: Text
    source: Literal["curated_repository"]
    source_path: Text
    title: Text
    document_type: DocumentType
    service_code: Text
    version: Text
    document_date: date
    access_class: AccessClass
    customer_account_id: UUID | None = None
    status: DocumentStatus
    superseded_by: Text | None = None
    fictional: Annotated[bool, Field(strict=True)]

    @field_validator("source_path")
    @classmethod
    def validate_source_path(cls, value: str) -> str:
        parts = value.split("/")
        if any(part in {"", ".", ".."} for part in parts) or any(
            char in value for char in ("\\", ":", "\x00")
        ):
            raise ValueError(
                "Source path must be a relative POSIX path without traversal"
            )
        return value

    @model_validator(mode="after")
    def validate_bindings(self) -> Self:
        account_scoped = self.access_class == AccessClass.CUSTOMER_ACCOUNT
        if account_scoped != (self.customer_account_id is not None):
            raise ValueError("Only account-scoped sources require a customer account")
        if (self.status == DocumentStatus.SUPERSEDED) != (
            self.superseded_by is not None
        ):
            raise ValueError("Only superseded sources require a replacement document")
        if self.superseded_by == self.document_id:
            raise ValueError("A document cannot supersede itself")
        return self


class MarkdownLocation(KnowledgeContract):
    kind: Literal["markdown"]
    heading_path: tuple[Text, ...]
    line_start: PositiveInt
    line_end: PositiveInt

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if self.line_end < self.line_start:
            raise ValueError("Line end must be at least line start")
        return self


class PDFLocation(KnowledgeContract):
    kind: Literal["pdf"]
    page_number: PositiveInt


type SourceLocation = Annotated[
    MarkdownLocation | PDFLocation, Field(discriminator="kind")
]


class PassageLocation(KnowledgeContract):
    document_id: Text
    version: Text
    location: SourceLocation
