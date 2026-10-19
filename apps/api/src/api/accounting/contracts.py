from datetime import datetime
from decimal import Decimal, localcontext
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, StrictInt, StrictStr, model_validator

from api.workflow.actions import ImmutableContract

Identifier = Annotated[StrictStr, Field(min_length=1, max_length=200)]
Count = Annotated[StrictInt, Field(ge=0, le=9_007_199_254_740_991)]
Rate = Annotated[Decimal, Field(ge=0, le=1_000_000, max_digits=20, decimal_places=12)]
Mode = Literal["offline", "live"]
Outcome = Literal[
    "started", "response_received", "refused", "provider_error", "timeout", "cancelled"
]


class Usage(ImmutableContract):
    input_tokens: Count
    output_tokens: Count
    total_tokens: Count
    cached_input_tokens: Count | None

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.total_tokens != self.input_tokens + self.output_tokens:
            raise ValueError("Inconsistent usage")
        if (
            self.cached_input_tokens is not None
            and self.cached_input_tokens > self.input_tokens
        ):
            raise ValueError("Invalid cached usage")
        return self


class ModelRate(ImmutableContract):
    provider: Literal["openai"] = "openai"
    model: Identifier
    input_per_million: Rate
    output_per_million: Rate
    cached_input_per_million: Rate | None = None


class Pricing(ImmutableContract):
    version: Identifier
    currency: Literal["USD"] = "USD"
    rates: Annotated[tuple[ModelRate, ...], Field(max_length=100)]

    @model_validator(mode="after")
    def unique_rates(self) -> Self:
        if len({item.model for item in self.rates}) != len(self.rates):
            raise ValueError("Duplicate model rate")
        return self


class Cost(ImmutableContract):
    usd: Annotated[Decimal, Field(ge=0, max_digits=40, decimal_places=18)]
    pricing_version: Identifier
    model: Identifier
    rate: ModelRate


def estimate(
    pricing: Pricing | None, model: str, usage: Usage | None, mode: Mode
) -> tuple[Cost | None, str]:
    if mode == "offline":
        return None, "offline"
    if usage is None:
        return None, "usage_unavailable"
    if pricing is None:
        return None, "pricing_unavailable"
    rate = next((item for item in pricing.rates if item.model == model), None)
    if rate is None:
        return None, "rate_unavailable"
    if usage.cached_input_tokens is None and usage.input_tokens:
        return None, "cached_usage_unavailable"
    cached = usage.cached_input_tokens or 0
    if cached and rate.cached_input_per_million is None:
        return None, "cached_rate_unavailable"
    with localcontext() as ctx:
        ctx.prec = 60
        amount = (
            (usage.input_tokens - cached) * rate.input_per_million
            + cached * (rate.cached_input_per_million or Decimal(0))
            + usage.output_tokens * rate.output_per_million
        ) / Decimal(1_000_000)
    return Cost(
        usd=amount, pricing_version=pricing.version, model=model, rate=rate
    ), "available"


class Attempt(ImmutableContract):
    id: UUID
    call_id: UUID
    parent_call_id: UUID | None = None
    request_id: UUID | None
    scope_type: Literal["intake", "evidence"]
    scope_id: UUID
    operation_id: UUID
    component: Literal["extraction", "analysis", "embedding"]
    provider_mode: Mode
    configured_model: Identifier
    resolved_model: Identifier | None = None
    prompt_id: Identifier | None
    prompt_version: Identifier | None
    attempt: Annotated[StrictInt, Field(ge=1)]
    outcome: Outcome = "started"
    started_at: datetime
    finished_at: datetime | None = None
    latency_ms: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None
    usage: Usage | None = None
    cost: Cost | None = None
    cost_status: Literal[
        "pending",
        "offline",
        "usage_unavailable",
        "pricing_unavailable",
        "rate_unavailable",
        "cached_usage_unavailable",
        "cached_rate_unavailable",
        "invalid_usage",
        "available",
    ] = "pending"
    pricing: Pricing | None = Field(default=None, exclude=True)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if (self.outcome == "started") != (self.finished_at is None):
            raise ValueError("Invalid attempt completion")
        if self.finished_at is not None and (
            self.finished_at < self.started_at or self.latency_ms is None
        ):
            raise ValueError("Invalid measured duration")
        if (self.cost is not None) != (self.cost_status == "available"):
            raise ValueError("Invalid estimate status")
        if self.cost is not None and self.provider_mode != "live":
            raise ValueError("Offline estimate")
        if self.cost is not None:
            if self.pricing is None:
                raise ValueError("Estimate has no saved pricing basis")
            calculated, _ = estimate(
                self.pricing,
                self.resolved_model or self.configured_model,
                self.usage,
                self.provider_mode,
            )
            if calculated != self.cost:
                raise ValueError("Estimate differs from saved basis")
        return self
