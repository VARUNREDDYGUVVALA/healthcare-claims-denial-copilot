# Data dictionary

All identifiers are stable within the default seeded extract. Dates use ISO 8601. Eligibility, authorization and policy periods include the start date and exclude the end date.

| DuckDB table | Identifier and fields |
| --- | --- |
| `claims` | `id`, fictional `member`, `payer`, `submitted` date |
| `lines` | `id`, `claim_id`, `procedure`, `service` date, billed `amount` in whole USD |
| `eligibility` | `id`, `member`, `payer`, coverage `starts` and `ends`, extract `recorded` date |
| `authorizations` | `id`, `member`, `payer`, `procedure`, authorization `starts` and `ends`, extract `recorded` date |
| `responses` | `id`, referenced `line_id`, `status`, recorded `reason` code, `received` date |
| `policies` | versioned `id`, `payer`, `procedure`, effective `starts` and `ends`, `section`, fictional `excerpt` |
| `decisions` | `id`, denied `line_id`, review `action`, optional `note` |

The importer accepts identical replays, rolls back conflicting IDs and invalid extracts, and retains unmatched payer responses. Each line has at most one response in this dataset. Claims with both approved and denied lines are partially denied. Other claims with unresolved lines are pending. An absent eligibility or authorization record can coexist with an approved response.
