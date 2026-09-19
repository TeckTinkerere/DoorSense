# Demo video script (target 2:40, limit 3:00)

Record the **hosted** URL if you have it, otherwise `http://127.0.0.1:8000` (run `scripts/start.ps1` first). Have ready: `Test.csv` (Door) and `acv_test_case.xlsx` (ACV) from the challenge data. Windows: `Win+G` (Game Bar) or OBS to record; speak while clicking.

| Time | On screen | Say |
|---|---|---|
| 0:00-0:15 | Home page, Door / ACV switch visible | "DoorLens turns train sensor streams into a short answer a maintainer can act on. Two subsystems: Door and ACV." |
| 0:15-0:55 | Door tab: drop in `Test.csv`, click Analyse; show cycle list and overview | "I drop in the continuous door recording. It finds every open and close movement, 38 here, and labels each Normal or Abnormal resistance." |
| 0:55-1:20 | Select an abnormal cycle; show current vs the normal reference band | "For any movement I can see the motor current against a normal reference, so the label is explainable." |
| 1:20-1:50 | Click "Challenge this result", pick current -5 %, run | "I can also test whether a label is fragile: this re-runs the same frozen model on a synthetic recording change. The original result is never altered." |
| 1:50-2:05 | Download door CSV / ZIP | "Exports are in the exact challenge format." |
| 2:05-2:35 | ACV tab: drop in `acv_test_case.xlsx`, Rank the cars; show top car, trend chart, table | "For ACV I upload the eight-car workbook. Each car's cabin temperature is compared with its own setpoint and with its peers. The most suspicious car is Car 01, with the full ranking, the evidence chart and the numbers." |
| 2:35-2:50 | Download `predictions.zip`, then open "How this works" | "One click gives the submission file, and a plain-language guide explains it to a first-time user." |
| 2:50-3:00 | Back to home | "Explainable, reproducible, and honest about its limits. Thank you." |

Do not quote accuracy on the test sets (there are no public labels). If you mention training-set results, say they are development results.
