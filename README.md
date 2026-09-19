# DoorLens

> **Nebula X 2026, PS3 submission** (Door + ACV). Write-up: [docs/WRITEUP.md](docs/WRITEUP.md) · Predictions: [`predictions/`](predictions/) (`door_predictions.csv`, `acv_predictions.csv`, `predictions.zip`) · Hosting steps: [docs/DEPLOY_GCP.md](docs/DEPLOY_GCP.md) · Video script: [docs/VIDEO_SCRIPT.md](docs/VIDEO_SCRIPT.md)

**DoorLens classifies recorded door movements and lets you explore whether explicit recording assumptions change a result.**

Upload recorded door telemetry, inspect each movement and its normal-reference trace, run a real synthetic sensitivity check, and download the unchanged original predictions. This is a local hackathon analysis tool. It has no connection to a train, platform door, signalling system, or operator maintenance system.

## Run on Windows

Prerequisites: **Python 3.12**, a supported **Node.js LTS** release (22.13 or newer), and **pnpm 11.19.0**, as pinned in `frontend/package.json`. Setup requires internet access for dependencies. Python packages are pinned in `requirements.lock`; frontend dependencies are pinned in `frontend/pnpm-lock.yaml`. Core operation uses local assets and frozen models after setup/build.

From PowerShell:

```powershell
Set-Location 'E:\Projects\DoorSense'
.\scripts\setup.ps1
.\scripts\build.ps1
.\scripts\start.ps1
```

Open **http://127.0.0.1:8000**. Stop the server with Ctrl+C. On subsequent launches, only `start.ps1` is needed; it does not install dependencies or fit models. The launcher binds to the loopback interface.

The scripts use an app-local `.venv`. Setup discovers a user Python 3.12 installation, the Windows Python launcher, or the available Codex bundled Python runtime. You can select an executable explicitly:

```powershell
.\scripts\setup.ps1 -PythonPath 'C:\path\to\Python312\python.exe'
```

pnpm is discovered on PATH or from the available bundled runtime. On a machine with ordinary Node.js, install the exact `packageManager` version in `frontend/package.json` using npm first. `setup.ps1 -SkipFrontend` installs only Python dependencies. If your local PowerShell policy blocks scripts, use a process-scoped policy only if your organisation allows it: `Set-ExecutionPolicy -Scope Process Bypass`.

## Use and demonstrate

1. Upload `..\NebulaX-Hackathon-ProblemStatement\PS3\02_Datasets\Door\Test.csv`, or load the clearly labelled development example.
2. Select a movement. Inspect its current, position and other recorded signals; compare current with a reference for that direction and model.
3. Choose **Challenge this result** and one of five explicit recording changes. The backend copies and rescales/resamples the selected cycle, then runs the same frozen classifier again.
4. Compare original and synthetic model scores and labels. A stable label does not establish correctness.
5. Download the original CSV or ZIP. Probes do not change their bytes.

The CSV header is exactly `start_time,end_time,prediction`. Its labels are `Normal` and `Abnormal resistance`. `predictions.zip` contains only `door_predictions.csv` at the ZIP root. Original timestamp strings are retained. The official exports contain no sensitivity annotations or additional columns. Test.csv is inspected only for input-format compatibility and frozen inference, never for model fitting or selection.

See [DEMO_SCRIPT.md](DEMO_SCRIPT.md) for a three-minute walkthrough and [LIMITATIONS.md](LIMITATIONS.md) before presenting results. Generated submission files and verification evidence belong in `artifacts/`; Test.csv has no supplied ground truth, so its classifications are not measured test accuracy.

## Architecture and model identities

```text
Browser: Next.js static export + React/Plotly, local assets
                     | same-origin /api requests
FastAPI / Uvicorn on 127.0.0.1:8000
  validate CSV -> segment recorded cycles -> frozen Python inference
                        |                         |
                  bounded memory            original predictions
                        |                         |
              copy + one synthetic probe    immutable CSV / ZIP
                        |
                  same frozen model
```

The static frontend is built into `frontend/out`. FastAPI serves it alongside `/api/*`; unknown API endpoints return JSON 404. The inference implementation remains Python/NumPy/pandas. Uploads do not train models or update reference profiles. There is no database, cloud service, authentication, or external AI API.

The packaged **final model** is fitted using the documented 110 labelled training cycles and is used for uploads. The separate **development fold-zero model** reproduces `train_seg_017`, held out from that fold's model fitting. Its selected example is already examined development evidence, not an independent validation sample. Every analysis and challenge carries its model identity. Model scores are uncalibrated.

Artifacts under `backend/doorlens/models` hold coefficients, feature order, preprocessing, direction-specific reference profiles, manifests and hashes. They are trusted bundled JSON, not upload-supplied models. The model-packaging command reads the existing research and training inputs without modifying them:

```powershell
# Reproduce and verify the bundled parameters and research parity.
.\.venv\Scripts\python.exe .\scripts\package_models.py --verify

# Explicitly regenerate model artifacts from the documented training procedure.
# This is a development operation, never part of application startup.
.\.venv\Scripts\python.exe .\scripts\package_models.py
```

`--verify` reconstructs models in a temporary directory for comparison. It needs the sibling research files and labelled training data. Runtime inference and the production launcher need only the bundled models. `build.ps1` verifies models by default; `-SkipModelVerification` is available for an already verified distribution without the research inputs. Packaging and verification write the parity report to `artifacts/parity-report.json`. Neither operation uses Test.csv for fitting or tuning.

The reproduction scripts look for the original challenge material at `..\NebulaX-Hackathon-ProblemStatement\PS3`. If it is elsewhere, set `DOORLENS_SOURCE_ROOT` to the PS3 directory containing `02_Datasets` and `research`. The packaged application itself does not require this external source bundle.

## Development and verification

```powershell
.\scripts\dev.ps1
.\scripts\test.ps1
```

Development runs the API locally and the Next development server with `NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000`. Backend logs go to `.local/`; restart the script after backend edits. The production build clears this override and uses relative URLs. Ctrl+C stops the development processes started by the script.

`test.ps1` runs Python tests, model parity verification and frontend type checking. Use `-SkipFrontend` or `-SkipModelVerification` only when intentionally running a partial check. Production compilation is `build.ps1`.

For integration checks, leave the built production application running with `start.ps1` in one terminal. In a second terminal, from the `DoorSense` repository root, run:

```powershell
.\.venv\Scripts\python.exe .\scripts\verify_local.py
node .\scripts\browser_check.mjs
```

`verify_local.py` connects to **http://127.0.0.1:8000**, uploads the supplied Train.csv and Test.csv through the real API, checks cycle inspection, all five probes, unchanged original exports, demo model selection and JSON API errors. It saves the exact Test.csv download bytes as `artifacts/door_predictions.csv` and `artifacts/predictions.zip`, plus measured API and HTTP timings in `artifacts/local-api-verification.json`. This script does not implement a second exporter. Use `--url http://127.0.0.1:8001` if the production launcher uses another port.

`browser_check.mjs` uses the pinned **Playwright 1.62.1** frontend development dependency and an installed Chrome or Edge browser. It exercises the real upload, charts, synthetic checks and downloads, deliberately delays a probe response to check selection changes, and checks representative desktop/laptop widths. It writes screenshots and `artifacts/browser-verification.json` only when the corresponding checks execute successfully. Browser failures produce `artifacts/browser-failure.json` and, where possible, a failure screenshot. Browser downloads used by the checks go to `.local/browser-downloads`.

Chrome and Edge are discovered at their standard installation locations. For a different browser path or server address:

```powershell
$env:DOORLENS_BROWSER = 'C:\path\to\chrome.exe'
$env:DOORLENS_URL = 'http://127.0.0.1:8001'
node .\scripts\browser_check.mjs
```

The browser check actively blocks requests to origins outside the chosen local application origin and fails on attempted external resources. This is a browser-session check of local operation; **the laptop is not disconnected from the network**. Merely launching headless Chrome is not evidence that the application workflow passed.

Completed on 18 September 2026: **32 Python tests passed**, frozen-model parity reproduced **2,091 comparisons** with maximum score difference **2.22 × 10⁻¹⁶**, and the production static build passed. The running API and Chrome browser both completed upload, inspection, real sensitivity checks and original downloads. Browser checks passed at 1440×1000, 1280×800 and 760×900, including delayed-response protection and refusal to download an expiry error as a prediction file. No external requests or unexpected browser errors occurred while external origins were blocked.

The measured Test.csv run processed 38 cycles in **588 ms** inside the API (**611 ms** including the local HTTP upload/response). Its outputs contain 30 `Normal` and 8 `Abnormal resistance` predictions. This is one laptop measurement and an unlabelled test prediction count, not field accuracy or a latency guarantee. See [VERIFICATION.md](VERIFICATION.md), [the parity report](artifacts/parity-report.json), [the API report](artifacts/local-api-verification.json) and [the browser report](artifacts/browser-verification.json). Two upstream test-client deprecation warnings remain; they do not affect the running application.

## Data lifecycle and configuration

The default limits are a **20 MiB file**, **300,000 rows**, **three retained analyses**, and **30 minutes per analysis**. Analyses are held in process memory; upload content is not saved as a product dataset. Multipart handling may spool an upload temporarily before the application reads it, and the application closes the upload. The size check is an application-file cap, not a hard network-ingress limit.

Expired analyses are refused on access and purged on the next store operation. Adding a fourth retained run evicts the oldest. A cleared, expired or evicted ID returns HTTP 410 during the same process lifetime; an unknown ID, including one from a previous server process, returns 404. Restarting clears all results. Download anything needed before clearing or stopping.

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `DOORLENS_MAX_UPLOAD_BYTES` | `20971520` | Maximum application-read file bytes |
| `DOORLENS_MAX_ROWS` | `300000` | CSV row cap |
| `DOORLENS_ANALYSIS_TTL_SECONDS` | `1800` | Retention time |
| `DOORLENS_MAX_ANALYSES` | `3` | Retained analysis count |
| `DOORLENS_MODEL_DIRECTORY` | bundled `backend/doorlens/models` | Trusted model directory override |
| `DOORLENS_FRONTEND_DIRECTORY` | `frontend/out` | Static frontend directory override |

Set variables before launching. Increased limits need their own memory/performance checks. `start.ps1 -Port 8001` changes the production port. This application is intended for one local review session, not internet hosting or shared production use.

## Troubleshooting

- **Missing Python/pnpm:** use the explicit Python path or install the declared prerequisites; rerun setup.
- **Missing static frontend:** run `build.ps1`. A backend-only start does not generate the user interface.
- **Model verification fails:** retain the failure output, check source files and dependency locks, and investigate the mismatch. Do not fit using uploads to suppress it.
- **Port in use:** stop the earlier local server or choose a different production `-Port`.
- **Upload rejected:** use the supplied door CSV format. Required channels must be numeric and finite, timestamps ordered, and movement blocks compatible with the recorded-cycle contract. Endpoint flags and time/movement structure are checked; position is not rejected merely for lying outside observed training endpoints. These checks cannot certify completeness or physical calibration of every unfamiliar recording. Renaming an arbitrary CSV does not make it supported telemetry.
- **Analysis expired:** upload again. Downloads always refer to the original result in the currently retained analysis.

Implementation details and endpoints are in [API_CONTRACT.md](API_CONTRACT.md). Research rationale remains in the sibling `research/` directory and is not modified by application use.

## ACV subsystem and combined submission

The **ACV** tab ranks the 8 cars of a train by refrigerant-leak likelihood from a telemetry workbook (`.xlsx` or `.csv`). Method: per-car indoor-minus-cooling-setpoint gap, mean/median/90th percentile turned into peer z-scores within the file. It has no fitted parameters. It scores 0.979 on the six labelled training cases (5 of 6 ranked first; the selection of these three summaries was made on those same cases, so treat it as optimistic). Output: `acv_predictions.csv` (`file_id,ranked_cars`). `GET /api/submission.zip?door=<id>&acv_id=<id>` bundles both subsystems' CSVs at the ZIP root.

Synthetic scenario testing against a live server (weaker leaks, moved leak, dropout, dead sensors, noise, 6-car trains, renamed columns, drifted Door gain/voltage, and more):

```powershell
.\.venv\Scripts\python.exe .\scripts\synthetic_eval.py --base http://127.0.0.1:8000
```

Results are written to `artifacts/synthetic-report.json`. The **How this works** page (`/how-it-works/`) is a plain-language guide for end users.

## Google Cloud (Cloud Run)

`Dockerfile` builds the frontend and API into one container. `scripts/deploy_gcp.ps1 -ProjectId <id>` deploys it to Cloud Run through Cloud Build. Analyses are held in memory, so the service is pinned to a single instance.
