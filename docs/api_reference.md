# API reference

| Operation | Endpoint | Role |
| --- | --- | --- |
| Start | `POST /api/investigations` with `{"line_id":"CLM-LEDGER-1"}` | Analyst or supervisor |
| Reopen | `GET /api/investigations/{id}` | Analyst or supervisor |
| Record final review | `POST /api/investigations/{id}/decision` with `{"decision":"approve","note":"Verified synthetic evidence."}` | Supervisor |

The OpenAPI schema is available at `GET /openapi.json`. In local mode, `GET /health` indicates whether the database, model, and metrics artifacts are available. Legacy claim endpoints retain their paths and require authentication when the local role tokens are configured.
