# DoorLens implementation plan

Goal: complete locally runnable application described in the external goal objective, not a scaffold. Original research and datasets remain read-only external verification inputs; packaged runtime inference is self-contained.

1. Freeze selected direction-specific phase logistic inference; reproduce all four development folds and signature results; package final and fold-zero demo models with checksums.
2. Validate CSV content and recorded-cycle contract, implement bounded immutable analysis store and exact CSV/ZIP APIs; separate development demo identity.
3. Implement all five copy/transform/rescore probes with original-data/export invariants.
4. Build static Next.js TypeScript/CSS Modules/Plotly workspace with stale-request protection and clear original/synthetic views.
5. Run meaningful model/API/export/limit/expiry tests, build frontend, exercise browser workflow and inspect desktop/laptop layouts. Fix discovered failures.
6. Package pinned dependencies, Windows setup/build/launch scripts, README/demo script; generate official Test exports through the application; audit every completion requirement.

Repository root is E:/Projects/DoorSense. The implementation was moved here from the challenge workspace while preserving its independent Git repository.

## Completion

All six implementation stages are complete. The production launcher and exact app-generated Test exports have been exercised; model, API and browser results are recorded in VERIFICATION.md and artifacts/*.json. No model retuning, Test fitting, live rail access or public deployment was performed.

Validation decisions: observed training endpoint ranges are descriptive rather than invented physical rejection limits. Unsupported movement structure is checked through timestamps, cadence, recorded endpoint states and direction consistency. Numerically overflowing derived features are rejected explicitly. Charts preserve timezone-free recorded coordinates and resize with their containers. Expired download responses cannot become counterfeit CSV/ZIP files.

## Shared integration contract

Python inference package: backend/doorlens/inference. Exposes InputError(code,message), parse_csv(content,max_rows), FrozenModel.load(directory), model.predict(cycle), model.reference(cycle), trace_payload(cycle), apply_probe(cycle,probe_id), PROBES. parse_csv returns tuple of pandas DataFrames with native Datetime and numeric _seconds; no fitting at runtime. Prediction is dict {prediction,score,direction}; reference contains progress,current_median_a,current_lower_a,current_upper_a,sample_count,provenance. trace contains time_ms,timestamps,current_a,voltage_v,back_emf,position,progress.

API response contract will be kept in API_CONTRACT.md. Model directories backend/doorlens/models/final and demo-fold-0. Demo source artifact backend/doorlens/models/demo.json. Provenance backend/doorlens/models/evidence.json. All models are trusted bundled JSON with manifest hashes.
