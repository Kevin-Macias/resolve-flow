from datetime import datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints

from api.services.schemas import Service
from api.user.schemas import User

type Description = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5_000)
]


class IssueReportStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    IN_REVIEW = "in_review"
    LINKED = "linked"
    DELETED = "deleted"
    CLOSED = "closed"


class IssueReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: Description
    affected_service_code: str | None = None


class IssueReportUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    affected_service_code: str | None = None


class IssueReportResponse(BaseModel):
    id: UUID
    customer_account_id: UUID
    description: Description
    affected_service: Service | None
    status: IssueReportStatus
    submitted_by: User
    created_at: datetime
    updated_at: datetime
