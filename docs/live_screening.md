# Live claim screening

Ledger’s **Live claim screening** page sends the entered claim line to FastAPI and displays the server’s recommendation and policy reference. It uses React and FastAPI and runs without paid model or payer API credentials. The screening route evaluates values in memory and does not write a claim record. The form accepts claim metadata and evidence flags. Leave names, health or member identifiers, and clinical notes out of this deployment.

## Run the full-stack app

From the repository root, set two distinct local role tokens:

```sh
export COPILOT_ANALYST_TOKEN="$(openssl rand -hex 32)"
export COPILOT_SUPERVISOR_TOKEN="$(openssl rand -hex 32)"
docker compose up --build --detach --wait --wait-timeout 180
```

Open `http://localhost:8000/`, select **Live claim screening**, and use the analyst token. The sample payer, plan, procedure, and service date are prefilled when the fictional catalogue is active. With coverage marked **Yes**, duplicate **No**, and authorization **No**, the example returns **Correct before submission**. Use an April 1, 2026 approval date with authorization **Yes** to pass the March 30 Version 1 checks. Unknown evidence or a missing policy requires review.

GitHub Pages is the static project website. The page detects that the API is unavailable there and gives setup instructions. To use the form on a public URL, deploy the application and API together behind the same HTTPS origin.

## Use an operator-maintained policy catalogue

The default synthetic catalogue provides reproducible examples. Set `COPILOT_SCREENING_POLICIES` to a local JSON file in the API process to load rules from a verified source maintained by your team. When using Compose, mount the catalogue read-only and pass the container path in the environment through a local override. A catalogue is an array of rules with these fields:

```json
[
  {
    "policy_id": "example-plan-rule-v1",
    "payer_code": "EXAMPLE",
    "plan_code": "PLAN-A",
    "procedure_code": "EXAMPLE-01",
    "effective_start": "2026-01-01",
    "effective_end": "2027-01-01",
    "authorization": "before_service",
    "max_units": 1,
    "source_url": "https://example.org/replace-with-payer-policy"
  }
]
```

Use the payer’s applicable programme, contract, policy version and source URL when maintaining rules. The engine matches payer, plan, procedure and service date using a start-inclusive, end-exclusive interval. The supported authorization rules are `not_required`, `before_service`, and `within_two_business_days`. The latter uses weekdays and does not incorporate a holiday calendar. An overlapping match produces a manual-review recommendation. The system records the supplied coverage, duplicate, authorization and coding evidence as inputs for screening and has no payer eligibility or adjudication connection. An authorized reviewer owns the final submission decision.

`GET /api/screening/capabilities` reports whether role authentication is configured. `POST /api/screening` requires a valid bearer token. The OpenAPI schema is at `/docs` on the API host.

Before accepting customer claim information on a public site, replace shared role tokens with individual identities, verify policy sources and payer access, and establish data handling, audit, retention, and hosting controls. This repository provides the local workflow and a static portfolio site.
