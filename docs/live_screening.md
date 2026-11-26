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

## Host a screening pilot over HTTPS

The Compose overlay uses Caddy for automatic TLS and exposes the web UI and screening routes through one origin. Other API routes, including the analyst and supervisor workflow, stay behind the proxy. Use this setup with fictional claim inputs while preparing customer access.

1. On a Linux host with Docker and Docker Compose v2.24.4 or later, clone the repository. Point a DNS hostname at that host and allow inbound TCP 80 and 443.
2. Copy `.env.example` to `.env`. Set the two distinct role tokens using independent `openssl rand -hex 32` outputs, add `COPILOT_HOST=claims.example.org` with your hostname, and run `chmod 600 .env`.
3. Start both services from the repository root:

   ```sh
   docker compose -f docker-compose.yml -f compose.https.yml up --build -d --wait --wait-timeout 300
   ```
4. Open `https://claims.example.org/` and select **Live claim screening**. Confirm the form connects and that changing the sample authorization evidence changes the recommendation. Confirm `/api/screening/capabilities` returns JSON and a request to `/api/screening` without a bearer token receives HTTP 401.

Keep the Caddy data volume across restarts to retain certificates. Use `docker compose -f docker-compose.yml -f compose.https.yml logs proxy copilot` to check startup or certificate issues.

## Enable the three workspaces

The account workspace is an opt-in, single-organization pilot. Use fictional inputs and separate accounts for each participant. Set `COPILOT_WORKSPACE_DB=/app/artifacts/workspace.sqlite3` in the Compose `.env` file and restart the services. The SQLite database lives in the persistent artifacts volume. Back it up alongside your other application data.

Provision an initial manager and a customer from a trusted server terminal. The command prompts for the password and stores a salted hash. Use `-f docker-compose.yml -f compose.https.yml` before `exec` for the HTTPS deployment.

```sh
docker compose exec copilot python -m scripts.create_workspace_account manager ledger-manager
docker compose exec copilot python -m scripts.create_workspace_account customer ledger-customer
```

Open **Claim workspace** in the sidebar.

1. Sign in as the customer and select **Analyze claim line**. Read the screening recommendation and matched policy, then select **Request analyst review** to save a case in **Your submissions**.
2. Sign in as the manager, activate an analyst account for a verified staff member, then open the case and assign it. The dashboard shows workload counts by review stage.
3. Sign in as that analyst. Open the assigned case and inspect the saved input and policy checks. Record a review outcome or escalate the case for the manager to resolve.
4. Sign in as the customer again and refresh the queue. Open the case to see the decision and status history.

Bearer sessions last eight hours and sign-out revokes the current session. The browser keeps the token in memory. Customers can access their own submissions, analysts can access assigned submissions, and managers can access the organization queue. Assignment, review, and escalation events are saved with their actor and timestamp. Workspace decisions are pre-submission recommendations. The existing fictional payer-response and three-year denial analytics remain in the portfolio demo. The account workspace has no live payer feed.

This pilot shares one organization database and uses manager-provisioned accounts. Customer onboarding still requires an approved hosting and data-handling setup, a managed identity lifecycle, and verified payer policies.
