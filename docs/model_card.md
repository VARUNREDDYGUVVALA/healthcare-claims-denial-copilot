# Denial ranking model card

The model uses logistic regression with a training-fitted `DictVectorizer`. Predictors are payer, procedure, missing matching eligibility, missing matching imaging authorization, and a possible duplicate. Evidence must be in the extract before submission. A possible duplicate uses an earlier submitted claim or a preceding line within the same claim. Responses, response reasons and analyst decisions supply no predictive features.

The chronological split uses submission dates. Training uses 2,674 finalized lines with both submission and response before September 1, 2025. The later holdout has 1,248 finalized lines, including 317 denials. Pending and walkthrough lines are excluded from evaluation. The rules baseline weights missing eligibility at 0.55, missing imaging authorization at 0.38, and possible duplicates at 0.48.

| Method | PR-AUC (average precision) | ROC-AUC | Precision at 3 reviews/day | Recall at 3 reviews/day |
| --- | ---: | ---: | ---: | ---: |
| Logistic regression | 0.7946 | 0.9270 | 66.04% | 66.25% |
| Rules baseline | 0.7126 | 0.9101 | 63.52% | 63.72% |

The logistic model’s Brier score on the holdout is **0.0841**. The rules produce ranking scores rather than calibrated probabilities.

Precision pools up to three top-ranked holdout lines per submission day and breaks ties by stable ID. Each method selects 318 lines. The holdout and dashboard cover the generated population eligible for their respective calculations. The browser queue includes all generated claim lines, including the walkthrough claims. Search and status filters apply to the entire ranked queue, which displays 25 lines per page.

Policy retrieval filters by payer, procedure and service date, then ranks sections by overlap with terms tied to the recorded reason. Each denial displays one suggested action. All explanations are deterministic and run locally.
