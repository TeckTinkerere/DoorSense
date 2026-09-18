# DoorLens verification record

Completed **18 September 2026**, using the packaged application at `http://127.0.0.1:8000`. This records software and dataset checks, not operational rail validation.

## Completed checks

| Requirement | Executed evidence |
| --- | --- |
| Frozen inference parity | 2,091 comparisons against original research and saved scores; maximum absolute score difference 2.220446049250313e-16, identical labels, tolerance 1e-9. All four development folds, all five fixed probes, final-model scores, and previously examined reserve regression outputs reproduced. |
| Model packaging | Separate final/all-110 and development/fold-0 JSON packages; checksummed manifests; training and evidence input hashes, ordered feature schema and dependencies recorded. `--verify` reconstructed the package without overwriting model artifacts. |
| Correct development example | `train_seg_017` uses fold 0 trained on zero-based indices 24–87. Dynamic original score 0.6369046416612815; current ×0.95 score 0.3600240212649819; label changes Abnormal resistance → Normal. |
| Backend/inference tests | 32 passed. Coverage includes native timestamp parsing, all supplied Train/Test cycles, malformed content, finite arithmetic overflow, unsupported movement structure, byte/row limits, model tampering, correct demo model, expiry/eviction, and API namespace protection. |
| Original data and export protection | Every probe preserves original cycle data and exact original CSV/ZIP bytes. Downloads use the cached result; no separate prediction/export implementation exists. |
| Production launch | Documented Windows `build.ps1` produced Next static output; `start.ps1` served that output and `/api/*` from one loopback Uvicorn process. Missing API routes returned JSON 404. |
| Real file processing | Running API accepted Train.csv (110 movements) and Test.csv (38 movements), inspected a cycle, ran all five probes, and served unchanged downloads. |
| Browser workflow | Chrome 153.0.8010.48, Playwright 1.62.1: actual Test upload, selected signals, current and voltage probes, saved methodology, CSV/ZIP downloads, malformed upload, separate development context. |
| Stale response protection | A real challenge response was deliberately delayed while switching through two other cycles. It did not appear on the newly selected cycle. |
| Expired download handling | API expiry was tested with an injected clock. Separately, a 410 response was injected at the browser download boundary; the UI displayed expiry and did not save JSON as a prediction file. |
| Charts and screen sizes | Inspected 1440×1000, 1280×800 and 760×900. Recorded wall-clock axis preserved; plots sized to containers; no document overflow or control overlap in the final captures. |
| Local-only browser operation | External origins actively blocked. No attempted external requests and no unexpected browser errors. The laptop's network connection itself was not disabled. |

The first browser round identified a timezone shift and chart overflow on resizing. Both were corrected together and the second round passed. Independent screenshot review identified the same two defects; the final captures show their correction. The model, features, selected regularisation and threshold were not changed for these UI fixes.

## Actual output files

- [door_predictions.csv](artifacts/door_predictions.csv): 38 predicted intervals; exact header `start_time,end_time,prediction`; 30 `Normal`, 8 `Abnormal resistance`.
- [predictions.zip](artifacts/predictions.zip): contains only `door_predictions.csv` at its root.
- CSV SHA-256: `2f94f8f5e2ccd6bce223a7c2f9fd2c7b974aa17cbce3d7bc3521dd100d7a079b`.

These files are the actual application's HTTP download bytes. The browser's separate download was byte-identical to both the API response and the saved official ZIP. Test labels are unavailable, so output counts establish no test accuracy.

| File | API processing | Local HTTP upload to response |
| --- | ---: | ---: |
| Train.csv | 1,567.539 ms | 1,614.358 ms |
| Test.csv | 588.424 ms | 610.841 ms |

One measured run per file on this machine, not a throughput benchmark. Browser chart rendering is outside the API processing duration.

## Reproduction and evidence

Run the Windows setup, build and launcher commands in [README.md](README.md). Automated checks:

```powershell
.\scripts\test.ps1
# In another terminal, with the production server running:
.\.venv\Scripts\python.exe .\scripts\verify_local.py
node .\scripts\browser_check.mjs
```

- [Model parity](artifacts/parity-report.json)
- [Running API checks and measured latency](artifacts/local-api-verification.json)
- [Browser checks and requested local paths](artifacts/browser-verification.json)
- [Desktop evidence view](artifacts/browser-signature-1440.png)
- [Laptop evidence view](artifacts/browser-signature-1280.png)
- [Narrow layout](artifacts/browser-responsive-760.png)
- [Saved methodology view](artifacts/browser-methodology-1440.png)

## Deliberate limits

The small reserve was previously examined. Reproducing it is a regression check, not a new holdout or another model-selection experiment. Original asset/run identities, hidden test answers, calibrated sensor tolerances, live MRT access and maintenance outcomes remain unavailable. Synthetic gain/sample-removal probes establish sensitivity only. See [LIMITATIONS.md](LIMITATIONS.md).

No demonstration video has been recorded. [DEMO_SCRIPT.md](DEMO_SCRIPT.md) provides the required at-most-three-minute recording storyline. The final submission still needs that video and the registered team folder arrangement described in the original specification; the app and prediction outputs are ready.

Two dependency deprecation warnings occur in the Python test client (HTTPX integration and an AnyIO alias); no application test failed. The initial browser failure artifacts, when present, are historical diagnostics superseded by the successful `browser-verification.json`.
