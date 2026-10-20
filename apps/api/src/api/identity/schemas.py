from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    EmailStr,
    Field,
    SecretStr,
    StringConstraints,
    field_validator,
    model_validator,
)

from api.intake.schemas import Contract

Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
NewPassword = Annotated[SecretStr, Field(min_length=15, max_length=128)]


class EmailContract(Contract):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.casefold()


class InvitationRequest(Contract):
    user_type: Literal["customer", "support"]
    customer_account_id: UUID | None
    support_account_ids: Annotated[list[UUID], Field(max_length=100)] = Field(
        default_factory=lambda: list[UUID]()
    )

    @model_validator(mode="after")
    def scope_matches_role(self) -> Self:
        if (self.user_type == "customer") != (self.customer_account_id is not None):
            raise ValueError("Customer account must match the chosen role")
        if self.user_type == "customer" and self.support_account_ids:
            raise ValueError("Customer invitations cannot contain support grants")
        if len(set(self.support_account_ids)) != len(self.support_account_ids):
            raise ValueError("Support grants must be unique")
        return self


class InvitationCreated(Contract):
    invitation_id: UUID
    token: str
    expires_at: datetime


class LoginRequest(EmailContract):
    password: Annotated[SecretStr, Field(min_length=1, max_length=128)]


class RedeemInvitation(EmailContract):
    token: Annotated[SecretStr, Field(min_length=1, max_length=256)]
    name: Name
    last_name: Name
    password: NewPassword


class LocalAccountInput(EmailContract):
    name: Name
    last_name: Name
    password: NewPassword


class AuthUser(EmailContract):
    id: UUID
    name: str
    last_name: str
    user_type: Literal["customer", "support"]
    customer_account_id: UUID | None
    is_admin: bool


class SessionCreated(Contract):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    user: AuthUser


class SupportGrantsRequest(Contract):
    account_ids: Annotated[list[UUID], Field(max_length=100)]

    @field_validator("account_ids")
    @classmethod
    def unique_accounts(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("Support grants must be unique")
        return value
