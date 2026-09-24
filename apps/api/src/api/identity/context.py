from dataclasses import dataclass
from typing import Literal
from uuid import UUID


@dataclass(frozen=True)
class RequestContext:
    user_id: UUID
    user_type: Literal["customer", "support"]
    customer_account_id: UUID | None
