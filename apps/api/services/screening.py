"""Deterministic, evidence-based live screening with locally configured policies."""
from datetime import timedelta
import os
from pathlib import Path

from pydantic import TypeAdapter

from apps.api.schemas.screening import ClaimScreening, ScreeningPolicy
from data.policies.catalog import policy_sections

POLICIES = TypeAdapter(list[ScreeningPolicy])


def policy_mode():
    return "configured" if os.environ.get("COPILOT_SCREENING_POLICIES") else "synthetic"


def load_policies():
    configured = os.environ.get("COPILOT_SCREENING_POLICIES")
    if configured:
        with Path(configured).open("rb") as source:
            data = source.read(2_000_001)
        if len(data) > 2_000_000:
            raise ValueError("The configured policy catalog exceeds 2 MB.")
        policies = POLICIES.validate_json(data)
        if not policies or any(not policy.source_url for policy in policies):
            raise ValueError("Configured policies require a source URL.")
        return policies

    return [
        ScreeningPolicy(
            policy_id=row["id"], payer_code="NORTHSTAR", plan_code="DEMO", procedure_code=row["procedure"],
            effective_start=row["starts"], effective_end=row["ends"],
            authorization=("not_required" if row["procedure"] != "IMG-01" else
                           "within_two_business_days" if row["id"].endswith("-v1") else "before_service"),
        )
        for row in policy_sections() if row["payer"] == "Northstar Health"
    ]


def two_weekdays_after(service):
    current = service
    remaining = 2
    while remaining:
        current += timedelta(days=1)
        remaining -= current.weekday() < 5
    return current


def evaluate_screening(claim: ClaimScreening, policies: list[ScreeningPolicy]):
    issues = []
    matches = [policy for policy in policies if (
        policy.payer_code == claim.payer_code and policy.plan_code == claim.plan_code
        and policy.procedure_code == claim.procedure_code
        and policy.effective_start <= claim.service_date < policy.effective_end
    )]
    policy = matches[0] if len(matches) == 1 else None

    def issue(code, severity, message):
        issues.append({"code": code, "severity": severity, "message": message})

    if not policy:
        issue("POLICY_AMBIGUOUS" if matches else "POLICY_UNAVAILABLE", "review",
              "Multiple rules matched. Verify the policy version." if matches else
              "No configured rule applies to this payer, plan, procedure and service date.")

    if claim.coverage_active == "no":
        issue("INACTIVE_COVERAGE", "correct", "Check the supplied inactive coverage before submission.")
    elif claim.coverage_active == "unknown":
        issue("COVERAGE_UNKNOWN", "review", "Verify coverage for the service date.")

    if claim.duplicate_confirmed == "yes":
        issue("DUPLICATE", "correct", "A duplicate was reported. Reconcile the original line before submission.")
    elif claim.duplicate_confirmed == "unknown":
        issue("DUPLICATE_UNKNOWN", "review", "Check whether the line has already been submitted.")

    if policy:
        if policy.max_units is not None and claim.units > policy.max_units:
            issue("UNIT_LIMIT", "correct", f"Entered units exceed the configured limit of {policy.max_units}.")
        if policy.authorization != "not_required":
            approval = claim.authorization_date
            if claim.authorization_present == "no":
                issue("AUTH_ABSENT", "correct", "The configured policy requires authorization, and none was reported.")
            elif not approval:
                issue("AUTH_UNKNOWN", "review", "Verify the authorization approval date.")
            elif policy.authorization == "before_service" and approval == claim.service_date:
                issue("AUTH_TIME_UNKNOWN", "review", "Same-day approval requires verifying that it preceded the service.")
            elif policy.authorization == "before_service" and approval > claim.service_date:
                issue("AUTH_LATE", "correct", "The approval date is after the service date.")
            elif policy.authorization == "within_two_business_days" and approval > two_weekdays_after(claim.service_date):
                issue("AUTH_LATE", "correct", "The approval date exceeds the configured two-weekday window.")

    if not policy:
        recommendation = "needs_review"
    elif any(item["severity"] == "correct" for item in issues):
        recommendation = "correct_before_submission"
    elif issues:
        recommendation = "needs_review"
    else:
        recommendation = "ready_for_review"
    return {"recommendation": recommendation, "issues": issues, "matched_policy": policy}
