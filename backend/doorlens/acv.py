"""ACV refrigerant-leak localisation: rank the 8 cars of a train by leak likelihood.

Method (deliberately simple, no fitted parameters, so nothing can leak from the
six training cases): an undercharged car cools poorly, so its cabin temperature
sits above its own cooling setpoint by more than its peers on the same train.
Each car gets the indoor-minus-setpoint gap over valid samples; three robust
summaries (mean, median, 90th percentile) become peer z-scores within the file
and are averaged into one leak score.
"""

from __future__ import annotations

import csv
import hashlib
from io import BytesIO, StringIO
import re
import secrets
from threading import Lock
import time
import zipfile

import numpy as np
import pandas as pd

from doorlens.inference import InputError

INDOOR = ("Indoor Average Temperature", "Passenger Cabin Temperature Detected Value")
SETPOINT = ("ACV Control Temperature (Cooling)", "Target Temperature Value")
CAR_COLUMN = re.compile(r"^Car (\d+) - (.+)$")
MIN_VALID_SAMPLES = 30
MIN_PLAUSIBLE_C = 5.0  # 0 / blank readings are sensor-invalid, not real 0 degC cabins
MODEL_ID = "acv-peer-gap-v1"


def read_table(content: bytes, filename: str) -> pd.DataFrame:
    name = filename.lower()
    try:
        if name.endswith((".xlsx", ".xlsm")):
            try:
                return pd.read_excel(BytesIO(content), engine="calamine")
            except ImportError:
                return pd.read_excel(BytesIO(content), engine="openpyxl")
        if name.endswith(".csv"):
            return pd.read_csv(BytesIO(content))
    except Exception as exc:  # unreadable workbook / malformed csv
        raise InputError("acv_unreadable", f"The file could not be read as a spreadsheet ({type(exc).__name__}).") from None
    raise InputError("acv_unsupported_type", "Upload an .xlsx (or .csv) ACV telemetry file.")


def car_ids(table: pd.DataFrame) -> list[str]:
    return sorted({m.group(1) for c in table.columns if (m := CAR_COLUMN.match(str(c)))})


def _column(table: pd.DataFrame, car: str, aliases: tuple[str, ...]):
    for alias in aliases:
        key = f"Car {car} - {alias}"
        if key in table.columns:
            return pd.to_numeric(table[key], errors="coerce")
    return None


def car_gap(table: pd.DataFrame, car: str):
    indoor, setpoint = _column(table, car, INDOOR), _column(table, car, SETPOINT)
    if indoor is None or setpoint is None:
        return None
    valid = (indoor > MIN_PLAUSIBLE_C) & (setpoint > MIN_PLAUSIBLE_C)
    return (indoor - setpoint).where(valid)


def _peer_z(values: pd.Series) -> pd.Series:
    known = values.dropna()
    spread = known.std(ddof=0)
    if len(known) < 2 or not spread > 0:
        return pd.Series(0.0, index=values.index)
    return (values - known.mean()) / spread


def rank_cars(table: pd.DataFrame, max_rows: int = 300_000) -> dict:
    if len(table) > max_rows:
        raise InputError("acv_too_large", f"The file has more than {max_rows:,} rows.")
    cars = car_ids(table)
    if len(cars) < 2:
        raise InputError("acv_no_cars", "No per-car columns named 'Car NN - <parameter>' were found; at least two cars are needed to compare peers.")
    gaps = {c: car_gap(table, c) for c in cars}
    if all(g is None for g in gaps.values()):
        raise InputError("acv_missing_signals", "No car has both an indoor temperature and a cooling setpoint column.")
    stats = {}
    for car, gap in gaps.items():
        x = gap.dropna() if gap is not None else pd.Series(dtype=float)
        if len(x) < MIN_VALID_SAMPLES:
            stats[car] = {"valid_samples": len(x), "gap_mean": np.nan, "gap_median": np.nan, "gap_p90": np.nan}
        else:
            stats[car] = {"valid_samples": len(x), "gap_mean": x.mean(),
                          "gap_median": x.median(), "gap_p90": x.quantile(0.9)}
    frame = pd.DataFrame(stats).T.astype(float)
    z = pd.concat([_peer_z(frame[k]) for k in ("gap_mean", "gap_median", "gap_p90")], axis=1).mean(axis=1)
    usable = frame["gap_mean"].notna()
    order = sorted(cars, key=lambda c: (not usable[c], -z[c] if usable[c] else 0.0, c))
    top = [z[c] for c in order if usable[c]]
    margin = float(top[0] - top[1]) if len(top) > 1 else 0.0

    def rounded(car, key):
        return round(float(frame.loc[car, key]), 3) if usable[car] else None

    return {
        "ranked_cars": order,
        "cars": [{"car": c, "rank": i + 1, "leak_score": round(float(z[c]), 4) if usable[c] else None,
                  "valid_samples": int(frame.loc[c, "valid_samples"]),
                  "gap_mean_c": rounded(c, "gap_mean"), "gap_median_c": rounded(c, "gap_median"),
                  "gap_p90_c": rounded(c, "gap_p90")} for i, c in enumerate(order)],
        "top_margin": round(margin, 3),
        "confidence": "clear" if margin >= 1.0 else "moderate" if margin >= 0.4 else "low",
        "n_rows": int(len(table)),
        "n_cars": len(cars),
        "unscored_cars": [c for c in cars if not usable[c]],
        "trend": trend_payload(table, gaps, order),
    }


def trend_payload(table: pd.DataFrame, gaps: dict, order: list[str], points: int = 160) -> dict:
    """Display-only: per-car gap averaged in roughly equal time buckets."""
    n = len(table)
    edges = np.unique(np.linspace(0, n, min(points, max(2, n // 5)) + 1, dtype=int))
    times = table["Time"].astype(str).tolist() if "Time" in table.columns else [str(i) for i in range(n)]
    labels = [times[min(int(a), n - 1)] for a in edges[:-1]]
    series = {}
    for car in order:
        g = gaps.get(car)
        if g is None:
            continue
        arr = g.to_numpy(dtype=float)
        vals = []
        for a, b in zip(edges[:-1], edges[1:]):
            seg = arr[a:b]
            seg = seg[~np.isnan(seg)]
            vals.append(None if len(seg) == 0 else round(float(seg.mean()), 3))
        series[car] = vals
    return {"labels": labels, "series": series}


def predictions_csv(file_id: str, ranked: list[str]) -> bytes:
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(("file_id", "ranked_cars"))
    writer.writerow((file_id, "|".join(ranked)))
    return stream.getvalue().encode("utf-8")


def zip_of(files: dict[str, bytes]) -> bytes:
    archive = BytesIO()
    with zipfile.ZipFile(archive, "w") as zipped:
        for name, data in files.items():
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            zipped.writestr(entry, data)
    return archive.getvalue()


class AcvStore:
    """Small TTL-bounded in-memory store of ACV results."""

    def __init__(self, max_count: int = 5, ttl_seconds: float = 1800):
        self.max_count, self.ttl = max_count, ttl_seconds
        self._runs: dict[str, tuple[float, bytes]] = {}
        self._lock = Lock()

    def put(self, csv_bytes: bytes) -> str:
        identifier = "acv-" + secrets.token_hex(12)
        with self._lock:
            now = time.time()
            self._runs = {k: v for k, v in self._runs.items() if v[0] > now}
            while len(self._runs) >= self.max_count:
                self._runs.pop(next(iter(self._runs)))
            self._runs[identifier] = (now + self.ttl, csv_bytes)
        return identifier

    def get(self, identifier: str) -> bytes | None:
        with self._lock:
            item = self._runs.get(identifier)
            if item and item[0] > time.time():
                return item[1]
            self._runs.pop(identifier, None)
            return None


def analyse(content: bytes, filename: str, store: AcvStore, max_rows: int) -> dict:
    started = time.perf_counter()
    result = rank_cars(read_table(content, filename), max_rows)
    csv_bytes = predictions_csv(filename, result["ranked_cars"])
    result.update({
        "id": store.put(csv_bytes), "filename": filename, "model_id": MODEL_ID,
        "input_sha256": hashlib.sha256(content).hexdigest(),
        "csv_sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        "warnings": ["Leak scores are relative peer comparisons within one file, not calibrated probabilities.",
                     "Each file is assumed to contain exactly one leaking car, as in the challenge data."],
    })
    return result
