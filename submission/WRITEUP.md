# DoorLens: Nebula X PS3 write-up

**Subsystems attempted: Door and ACV** (2 of 4). One web app, one `predictions.zip`.

## Solution in one paragraph
DoorLens is a local-first web app for train condition monitoring. Drop in a door-motor recording and it finds every open/close cycle and labels it *Normal* or *Abnormal resistance*. Drop in an ACV telemetry workbook and it ranks the eight cars from most to least likely to have the refrigerant leak. Each result comes with the evidence behind it (signal traces against a normal reference; a per-car temperature-gap chart), a CSV export in the exact challenge format, and plain-language limits.

## Door: segmentation + classification
- **Segmentation.** The stream is cut into cycles at recording-gap boundaries; a cycle's start/end timestamps are taken from the recorded rows, so boundaries are exact. On `Train.csv` this reproduces all 110 labelled segments with IoU 1.0.
- **Classifier.** Direction-specific (open / close) logistic regression on 12 cycle summaries plus 9 relative-travel residuals against a normal-reference profile, L2 = 1, threshold 0.5. Frozen JSON coefficients, pure NumPy inference, no external service.
- **Validation (no leakage).** 88 development cycles were evaluated in four ordered folds (e.g. fold 0 is fitted on indices 24-87 and scores the held-out 0-23), with a further 22-cycle reserve; normal-reference profiles come from labelled normal training cycles of the model being evaluated, and `Test.csv` is never used for fitting or selection. Development fold results: 88/88 for the phase model (current-only baseline 87/88, abnormal recall 95.7%, false-alarm rate 0). Reserve: 22/22. The reserve was examined during development, so it is not an independent holdout. Original door, session and fault identities are not in the data, so neighbouring cycles may be correlated and these numbers can be optimistic.
- **Score on the training stream:** IoU-weighted F1 = 1.000 (the final model is fitted on these 110 cycles, so this shows segmentation, not generalisation). `Test.csv` yields 38 cycles (30 Normal, 8 Abnormal); it has no public labels.
- **Robustness check (synthetic).** Re-running perturbed copies of the training stream through the live app: halves/subsets, current noise (sd 15 mA), current ×1.15, normal-only and abnormal-only streams all keep F1 ≥ 0.99. Current ×0.85 gives 0.94 and **voltage +10 % drops to 0.82**: the Door model is sensitive to voltage gain drift.

## ACV: leak localisation by peer comparison
Six training cases are too few to fit a model without overfitting, so the method has no fitted parameters. An undercharged car cools poorly: its indoor temperature sits above its own cooling setpoint by more than its peers'. For every car, over valid samples, we take the indoor-minus-setpoint gap, summarise it (mean, median, 90th percentile), convert each to a peer z-score within the file, and average. Cars with no valid data are ranked last. Column aliases handle the richer 483-column file.
- **Training cases:** true car ranked first in 5 of 6, second in the other; mean rank-decay score **0.979**. We chose the three summaries after looking at these same six cases, so treat it as optimistic.
- **Test file (`acv_test_case.xlsx`):** `01|03|07|04|08|06|02|05` with a moderate lead.
- **Synthetic scenarios (51):** leak moved to another car, half-strength leak, sensor dropout, dead healthy sensor, noise, 6-car train, renamed columns, first-quarter-only, `.xlsx` round-trip. 49 met expectations, mean score 0.986; 5/5 bad inputs give clean errors. Known limit: on a train with no leak it still names a top car, and its lead size cannot reliably say "no leak" (the task guarantees exactly one leak).

## What is different about it
1. Explainable by design: every answer shows the signals behind it and a normal reference.
2. A "Challenge this result" tool re-runs the frozen classifier on an explicitly synthetic recording change (current/voltage ±5 %, dropped samples) so users see whether a label is fragile.
3. Honest scope: uncalibrated scores are labelled as such, and the limits page says what has not been established.
4. Reproducible: pinned dependencies, checksummed models, parity report against the research pipeline, live-server synthetic test harness (`scripts/synthetic_eval.py`), and a browser test.

## Tech stack
Python 3.12, FastAPI/Uvicorn, NumPy/pandas (+ calamine for fast `.xlsx`), Next.js (static export) + React + Plotly, pytest (43 passing) and Playwright checks, Docker + Google Cloud Run for hosting.

## Assumptions and limits
- Door segmentation relies on the recording-gap convention of the supplied streams; it is not validated for live telemetry.
- "Abnormal resistance" is the dataset label, not a diagnosed root cause. Nothing here is a safety or departure-authorisation decision.
- ACV assumes exactly one leaking car per file.
- No claim is made about accuracy on the held-out test sets; they were used for inference only and never for fitting or tuning.
