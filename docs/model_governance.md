# Denial model governance

Ledger’s **Manager dashboard → Model governance** shows a credential-free evaluation snapshot with validation and frozen-test results. The queue still uses its existing logistic regression artifact. This comparison fits a separate logistic reference on the earlier experiment window so all learned models use the same training records.

## Experiment design

- Train on 1,958 lines submitted before July 1, 2025 whose outcomes were available before that date.
- Validate on 601 lines submitted from July 1 through August 31 with outcomes available before September 1.
- Test on 1,248 finalized lines submitted from September 1 onward. Pending outcomes and guided claims are excluded. Earlier claims whose labels arrived after a boundary are excluded from the preceding window.
- Fit vocabulary and model parameters on training only. Compare seeded random forest and histogram gradient boosting against logistic regression and the existing rules baseline. Rank three finalized lines per submission day with stable ID tie-breaking.
- On validation, require at least 0.005 PR-AUC improvement, no loss in precision at capacity, and no increase in Brier score. If multiple challengers pass, the highest validation PR-AUC wins. The frozen test checks that single candidate for regressions. It does not choose a replacement challenger.

## Measured result

| Model | Validation PR-AUC | Frozen-test PR-AUC | Frozen-test precision at 3/day | Frozen-test Brier |
| --- | ---: | ---: | ---: | ---: |
| Logistic reference | 0.7785 | 0.7918 | 66.04% | 0.0847 |
| Random forest | 0.7617 | 0.7463 | 66.35% | 0.0868 |
| Histogram gradient boosting | 0.7885 | 0.7727 | 66.98% | 0.0855 |
| Rules baseline | 0.6864 | 0.7126 | 63.52% | — |

Gradient boosting passed validation. On frozen test it improved precision at daily capacity, but both PR-AUC and Brier score regressed relative to the experiment reference. The release decision is **retain logistic regression**. Random forest failed the validation PR-AUC and capacity-precision gates. The dashboard publishes each criterion so the trade-off is visible.

Calibration buckets and payer/procedure slices describe the validation-selected model on frozen test. The drift table compares the prevalence of the three binary evidence features in training and test. An absolute change of ten percentage points triggers an alert. It is a retrospective synthetic diagnostic rather than a continuous monitor.

## Reproduce

```bash
python -m scripts.generate_data
python -m scripts.evaluate_challengers
```

The export includes a SHA-256 fingerprint of experiment window assignments, point-in-time input features, and outcome labels. CI rebuilds the snapshot, checks for differences, and uploads both evaluation reports. These synthetic results support a portfolio demonstration. A real rollout would require independently sourced and governed data, a shadow deployment, and an accountable promotion decision.
