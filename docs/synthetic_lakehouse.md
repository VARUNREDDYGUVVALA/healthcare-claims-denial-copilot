# Synthetic claims lakehouse

The batch generator produces a local Parquet snapshot. It uses set-based DuckDB SQL with deterministic IDs, a seed, and a bounded working memory setting. The public Ledger demo keeps its existing compact export and model artifacts.

| Preset | Claim lines | Claims | Fictional members | Service months |
| --- | ---: | ---: | ---: | ---: |
| Small | 5,000 | 1,250 | 250 | 12 |
| Medium | 100,000 | 25,000 | 5,000 | 24 |
| Large | 1,000,000 | 250,000 | 50,000 | 36 |

Every claim has four lines. Service dates start January 1, 2023. Submission, response, payment, and appeal events can occur after the service date window ends.

## Run

```bash
python -m scripts.generate_lakehouse --preset large
python -m scripts.generate_lakehouse --preset medium --seed 21 --output artifacts/custom-medium
```

The default output is `artifacts/lakehouse/<preset>-seed-<seed>/`. Generation stages files beside the destination and publishes the directory after validation. Repeating an invocation validates the file hashes and reuses the snapshot. Use a new destination to generate a different identity. The manifest captures counts, date bounds, validation results, and SHA-256 checksums. This is a batch snapshot pipeline.

## Tables

| Layer | Tables | Grain |
| --- | --- | --- |
| Bronze | `payers`, `plans`, `members`, `providers` | One per dimension ID |
| Bronze | `eligibility`, `policies` | One eligibility interval per member and one effective policy version per plan/procedure/interval |
| Bronze | `claims`, `claim_lines` | Claim header and four adjudicable lines per claim |
| Bronze | `authorizations`, `responses`, `payments`, `appeals` | One row per applicable line and event type. Pending responses have no receipt date. |
| Silver | `line_fact.parquet` | One row per claim line with service-date policy, point-in-time evidence, and recorded outcomes |
| Gold | `monthly_revenue.parquet` | Service month, payer, and procedure. Totals include line counts and billed, denied, and paid amounts in integer cents. |

For model experiments, `recorded_status`, `recorded_reason`, `received`, `paid_cents`, and `appeal_status` are outcomes or post-submission data. Exclude them from pre-submission features. Synthetic payment amounts and payer behavior are deterministic scenario rules.

## Verified large snapshot

Seed 43 generated service dates from **January 1, 2023 through December 31, 2025**. Reading the published Silver Parquet independently confirmed **1,000,000 lines**, **250,000 distinct claims**, **50,000 distinct members**, and **36 distinct service months**. It contained 911,153 approved, 68,907 denied, and 19,940 pending lines. The 14 compressed Parquet files used 16,908,764 bytes in this run. The validation manifest passed the count, key, policy, event, and aggregate reconciliation checks.

```sql
SELECT recorded_status, count(*) AS lines
FROM read_parquet('artifacts/lakehouse/large-seed-43/silver/line_fact.parquet')
GROUP BY recorded_status
ORDER BY recorded_status;
```

GitHub Actions generates all three presets and attaches their manifests. Parquet snapshots stay in ignored local artifacts.
