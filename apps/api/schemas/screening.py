"""Structured pre-submission inputs and explicit versioned policy rules."""
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

Code = Annotated[str, Field(min_length=1, max_length=30, pattern=r"^[A-Z0-9][A-Z0-9._-]*$")]
ServiceDate = Annotated[date, Field(ge=date(1900, 1, 1), le=date(2100, 12, 31))]
Evidence = Literal["yes", "no", "unknown"]


class ClaimScreening(BaseModel):
    model_config = ConfigDict(extra="forbid")
    payer_code: Code
    plan_code: Code
    procedure_code: Code
    service_date: ServiceDate
    units: Annotated[int, Field(strict=True, ge=1, le=9999)]
    coverage_active: Evidence
    authorization_present: Evidence
    authorization_date: ServiceDate | None = None
    duplicate_confirmed: Evidence

    @model_validator(mode="after")
    def authorization_consistency(self):
        if self.authorization_date and self.authorization_present != "yes":
            raise ValueError("An approval date requires authorization evidence marked yes.")
        return self


class ScreeningPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    policy_id: Annotated[str, Field(min_length=1, max_length=100)]
    payer_code: Code
    plan_code: Code
    procedure_code: Code
    effective_start: date
    effective_end: date
    max_units: Annotated[int, Field(strict=True, ge=1, le=9999)] | None = None
    authorization: Literal["not_required", "before_service", "within_two_business_days"]
    source_url: HttpUrl | None = None

    @model_validator(mode="after")
    def valid_interval(self):
        if self.effective_start >= self.effective_end:
            raise ValueError("Policy end must follow its effective start.")
        return self
