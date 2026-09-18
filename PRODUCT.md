# DoorLens product brief

Confirmed from the supplied goal: DoorLens classifies recorded door movements and lets users explore whether explicit recording assumptions change a result. The primary task is upload, inspect, challenge, then download unchanged original predictions. It is an offline laptop analytical tool, with a frozen Python model and a Next.js interface. No account, external service or training on uploads is involved.

The intended users are hackathon reviewers and analysts inspecting the supplied door CSV format. A useful result connects a classification to the actual waveform, an explicitly synthetic sensitivity check and a reproducible export. It does not imply a physical component diagnosis, calibrated confidence, safe departure, future failure prediction or field accuracy.

Confirmed constraints: maintain separate uploaded and development-demo contexts; retain model identity; keep original downloads available during probes; treat saved evaluation as saved evaluation; display counts and native timestamps honestly; label position in counts. All five named probes are fixed assumptions, applied after segmentation.

Assumptions made under the user's authorization for independent choices: desktop/laptop is primary; keyboard and narrow-screen access remain supported; the workspace keeps the latest upload and development example in separate tabs for the lifetime of the page; no persistent browser storage is needed. File validation and session expiry remain the API's authority.

Success: a first-time reviewer can upload a file, identify an abnormal cycle, understand a real computed sensitivity change, switch back to their upload, and download the original CSV/ZIP without mistaking synthetic output for submission output.
