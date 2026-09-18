"""One original result, one export, and isolated synthetic comparisons."""

import csv
from datetime import datetime, timezone
import hashlib
from io import BytesIO, StringIO
import json
from pathlib import Path
from threading import Lock
import time
import zipfile

import numpy as np

from doorlens.inference import FrozenModel, PROBES, apply_probe, parse_csv, trace_payload
from doorlens.services.store import Analysis, AnalysisStore


CAVEAT = (
    "Synthetic sensitivity check of an already segmented cycle. This assumed "
    "recording change is not a verified sensor tolerance. An unchanged label "
    "does not establish correctness; model scores are uncalibrated."
)


def iso_time(seconds: float) -> str:
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat().replace("+00:00", "Z")


def official_exports(cycles: list[dict]) -> tuple[bytes, bytes]:
    """Build once; downloads return these bytes without running inference."""
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(("start_time", "end_time", "prediction"))
    writer.writerows((row["start_time"], row["end_time"], row["prediction"]) for row in cycles)
    csv_bytes = stream.getvalue().encode("utf-8")
    archive = BytesIO()
    entry = zipfile.ZipInfo("door_predictions.csv", date_time=(1980, 1, 1, 0, 0, 0))
    entry.compress_type = zipfile.ZIP_DEFLATED
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr(entry, csv_bytes)
    return csv_bytes, archive.getvalue()


def overview_payload(cycles: tuple, target_points: int = 2400) -> dict:
    """Display-only decimation, preserving every cycle's ends and gap breaks."""
    result = {name: [] for name in ("time_ms", "timestamps", "current_a", "voltage_v", "back_emf", "position", "progress")}
    per_cycle = max(2, target_points // len(cycles))
    for index, cycle in enumerate(cycles):
        if index:
            for values in result.values():
                values.append(None)
        trace = trace_payload(cycle)
        keep = np.unique(np.linspace(0, len(cycle) - 1, min(per_cycle, len(cycle)), dtype=int))
        for name, values in result.items():
            values.extend(trace[name][int(i)] for i in keep)
    return result


class AnalysisService:
    def __init__(self, settings, store: AnalysisStore, models: dict | None = None):
        self.settings = settings
        self.store = store
        self._models = dict(models or {})
        self._model_lock = Lock()

    def model(self, context: str):
        key = "demo-fold-0" if context == "development-demo" else "final"
        with self._model_lock:
            if key not in self._models:
                self._models[key] = FrozenModel.load(Path(self.settings.model_directory) / key)
            return self._models[key]

    def analyze(self, content: bytes, filename: str, context: str = "upload",
                cycle_id: str | None = None) -> Analysis:
        started = time.perf_counter()
        cycles = parse_csv(content, max_rows=self.settings.max_rows)
        model = self.model(context)
        cycle_rows = []
        for index, cycle in enumerate(cycles):
            predicted = model.predict(cycle)
            cycle_rows.append({
                "index": index,
                "cycle_id": cycle_id if cycle_id is not None and len(cycles) == 1 else f"cycle_{index + 1:03d}",
                "start_time": str(cycle.Datetime.iloc[0]),
                "end_time": str(cycle.Datetime.iloc[-1]),
                "prediction": predicted["prediction"],
                "score": float(predicted["score"]),
                "direction": predicted["direction"],
                "sample_count": len(cycle),
                "duration_s": float(cycle._seconds.iloc[-1] - cycle._seconds.iloc[0]),
            })
        csv_bytes, zip_bytes = official_exports(cycle_rows)
        now = self.store.clock()
        expires = now + self.store.ttl_seconds
        identifier = self.store.new_id()
        normal_count = sum(row["prediction"] == "Normal" for row in cycle_rows)
        overview = overview_payload(cycles)
        warnings = [
            "Offline classification of recorded movements; model scores are uncalibrated.",
            "The recording-gap segmentation rule supports the supplied dataset structure, not arbitrary live streams.",
            "Analyses expire after the stated time; opening more runs may remove the oldest run.",
        ]
        if context == "development-demo":
            warnings.insert(0, "Recorded development example selected after exploratory evaluation; uses its original fold model, not the upload model.")
        response = {
            "id": identifier,
            "filename": filename,
            "context": context,
            "model_id": model.model_id,
            "model_label": model.metadata.get("model_label", model.model_id),
            "created_at": iso_time(now),
            "expires_at": iso_time(expires),
            "input_sha256": hashlib.sha256(content).hexdigest(),
            "csv_sha256": hashlib.sha256(csv_bytes).hexdigest(),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            "summary": {"cycle_count": len(cycles), "normal_count": normal_count,
                        "abnormal_count": len(cycles) - normal_count},
            "warnings": warnings,
            "cycles": cycle_rows,
            "overview": overview,
            "probe_definitions": PROBES,
        }
        analysis = Analysis(identifier, expires, model, cycles,
                            json.dumps(response, allow_nan=False, separators=(",", ":")).encode("utf-8"),
                            csv_bytes, zip_bytes)
        self.store.put(analysis)
        return analysis

    def demo(self) -> Analysis:
        source = json.loads((Path(self.settings.model_directory) / "demo.json").read_text(encoding="utf-8"))
        stream = StringIO(newline="")
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(source["columns"])
        writer.writerows(source["rows"])
        return self.analyze(stream.getvalue().encode("utf-8"), "Recorded development example · train_seg_017",
                            "development-demo", source["cycle_id"])

    @staticmethod
    def cycle_result(analysis: Analysis, index: int) -> dict:
        payload = json.loads(analysis.response_json)
        return {"analysis_id": analysis.id, "index": index, "context": payload["context"],
                "model_id": analysis.model.model_id, "cycle": payload["cycles"][index],
                "trace": trace_payload(analysis.cycles[index]),
                "reference": analysis.model.reference(analysis.cycles[index])}

    @staticmethod
    def challenge(analysis: Analysis, index: int, probe_id: str) -> dict:
        definition = next(probe for probe in PROBES if probe["id"] == probe_id)
        # Defend the authoritative original even if a future probe edits in place.
        altered_cycle = apply_probe(analysis.cycles[index].copy(deep=True), probe_id)
        altered = analysis.model.predict(altered_cycle)
        payload = json.loads(analysis.response_json)
        original = payload["cycles"][index]
        return {
            "analysis_id": analysis.id, "index": index, "model_id": analysis.model.model_id,
            "probe_id": probe_id, "probe_label": definition["label"], "description": definition["description"],
            "original": {"prediction": original["prediction"], "score": original["score"]},
            "altered": {"prediction": altered["prediction"], "score": float(altered["score"])},
            "label_changed": original["prediction"] != altered["prediction"],
            "trace": trace_payload(altered_cycle), "sample_count": len(altered_cycle),
            "original_csv_sha256": payload["csv_sha256"], "synthetic": True, "caveat": CAVEAT,
        }
