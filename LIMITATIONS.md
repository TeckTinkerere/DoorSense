# What DoorLens establishes—and what it does not

DoorLens implements reproducible offline classification and synthetic sensitivity checks on the supplied recorded door data. Its software workflow can be verified. Real MRT maintenance or safety performance has not been established.

## Dataset and evaluation

- There are 110 labelled training movement intervals (80 Normal, 30 Abnormal resistance), with a small previously examined development/reserve history. The ordered reserve is not a fresh holdout.
- The CSV lacks original door, vehicle, collection-session and fault-instance identities. Recorded order does not establish future operational chronology or independence between nearby cycles. Similar movements can make validation optimistic even without exact duplicate cycles.
- The supplied Test.csv has no accessible ground truth. Export counts and successful file generation are not test accuracy.
- The final model uses all labelled training cycles. The selected development demo uses a separate fold model and a previously examined example; it is not an independent test of generalisation.
- Saved development comparison counts and probe-change rates apply to that documented procedure and dataset. They do not establish field failure detection rates, prevalence, false-alarm frequency, or performance on another fleet.

## Signals, segmentation and interpretation

- Segmentation uses the recording's time-gap convention. It is not validated for continuous live telemetry, overlapping cycles, arbitrary idle samples, reversed time, incomplete movements or unrelated CSV schemas.
- Validation checks recorded state flags, timestamps, sampling and movement structure. It cannot certify the completeness or physical position scale of every new recording. The observed training endpoint range is descriptive metadata, not an invented physical limit. Inspecting Test.csv for format compatibility does not fit or select the classifier.
- A model score is an uncalibrated numerical output. It is not a probability that a passenger is safe or a component has failed.
- “Abnormal resistance” is the dataset label. It does not identify a worn roller, motor fault, obstruction, entrapment, or root cause.
- Normal-reference profiles are derived from labelled normal training recordings for the applicable model and direction. Their spread is not a tolerance band or safe operating envelope.
- Current is displayed in amperes using the documented channel scaling; voltage uses its recorded scaling. Position remains counts and back-EMF remains the recorded quantity. No calibrated force, distance, contact threshold, wear rate, or remaining useful life is inferred.

## Sensitivity probes

- Probes test classification of an already segmented cycle. They do not test the robustness of timestamp parsing or segmentation end to end.
- Current ×0.95/1.05 and voltage ×0.95/1.05 are explicit synthetic assumptions, not measured sensor error limits. They change the recording input, not a validated physical simulation of a door fault.
- Sample removal drops interior indices 20, 40, 60, and so on, preserving the original endpoints. This is one deterministic resampling pattern, not every possible missing-data condition.
- A stable prediction can still be wrong. A label change is a sensitivity observation, not proof that the original label is wrong.
- Five probes do not measure all uncertainty or establish robustness outside those probes. The selected demonstration must be shown with the aggregate research context.

## Deployment and data handling

- No train, door rig, depot, signalling or live operator connection is available. No interlocks are controlled or bypassed. This tool cannot issue a “safe to depart” decision or certified maintenance instruction.
- It is a single local process with bounded memory, no authentication and no persistent analysis database. It is not engineered as a shared or publicly exposed service.
- The default upload cap is enforced as the application reads the file. Multipart processing may have received/spooled data earlier; this is not a hard inbound transport cap.
- Expiry is checked when data is accessed; physical cleanup happens on subsequent store activity. Restarting discards all analysis IDs and results.
- Python and frontend installation/build need dependencies. Core runtime is designed to use only local assets; any completed external-request inspection or disconnected test must be recorded as an actual check, not inferred from the design.
- Latency depends on file size, hardware, concurrent work and limits. Only measured runs in verification artifacts can support a latency statement. No unmeasured service-level target is claimed.

## What would be needed next

An operator-facing evaluation needs independent recordings with real door/run/fault identities, verified channel definitions and calibration, representative normal variation, clear maintenance outcomes, and a locked evaluation plan. Any later operational or safety application also needs its own engineering review, integration constraints and approvals. Those are future validation dependencies, not completed work or hackathon performance claims.
