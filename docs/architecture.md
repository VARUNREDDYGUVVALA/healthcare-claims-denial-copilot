# Architecture

```mermaid
flowchart LR
    A[Seeded Python generator] --> B[Validated transactional DuckDB import]
    B --> C[Pre-submission features]
    C --> D[scikit-learn training and holdout evaluation]
    B --> E[Date-filtered policy retrieval]
    D --> F[Model and metrics artifacts]
    B --> G[FastAPI local API]
    F --> G
    E --> G
    D --> H[Static demo export]
    E --> H
    H --> I[React and Vite build]
    I --> J[GitHub Pages]
    J --> K[Browser-local review history]
```

## Repository map

| Area | Working code |
| --- | --- |
| Web and API | `apps/frontend` and `apps/api` |
| Synthetic data and ETL | `data/generator`, `data/policies`, and `data_engineering/ingestion` |
| Model | `machine_learning/{feature_engineering,training,evaluation}` |
| Policy evidence | `generative_ai/retrieval` and `evaluation/{rag,golden_datasets}` |
| Investigation | `agentic_ai/workflows`, approval routes, and local DuckDB |
| MCP | `mcp_server/server.py` |
| Delivery | `infrastructure/docker`, `docker-compose.yml`, and reusable workflows |
| Verification | `tests/{unit,integration,contract,e2e}` |

The proposed lakehouse and streaming adapters, production observability, Terraform, Kubernetes, Helm, and hosted LLM components remain roadmap items. Generated databases and models live under ignored `artifacts/`.
