# Investigation workflow

The Pages demo runs from a reproducible export. The local API adds a deterministic LangGraph investigation with evidence intake, service-date citation verification, conditional appeal drafting, and an analyst-to-supervisor handoff. The appeal is an internal draft. The API never transmits it to a payer.

```mermaid
flowchart LR
  A[Recorded fictional denial] --> B[Claims intake]
  B --> C[Verify policy and supporting evidence]
  C -->|Verified rebuttal evidence| D[Prepare appeal draft]
  C -->|Evidence gap or other investigation| E[Record evidence findings]
  D --> F[(DuckDB awaiting-review checkpoint)]
  E --> F
  F --> G[Supervisor decision]
  G --> H[(Final status and audit event)]
```
