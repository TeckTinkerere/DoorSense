"""Build synthetic scenarios from the supplied example data and test them against a LIVE server.

    python scripts/synthetic_eval.py --base http://127.0.0.1:8001

Truth is known for every scenario because each is derived from a labelled
Train case by a documented transformation. Files are written to
artifacts/synthetic/ and a report to artifacts/synthetic-report.json.
Door scenarios derive from Train.csv, which the final Door model was fitted on,
so they measure robustness to perturbation, not fresh generalisation.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import re
import sys

import numpy as np
import pandas as pd
import httpx

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get("DOORLENS_SOURCE_ROOT", ROOT.parent / "NebulaX-Hackathon-ProblemStatement" / "PS3"))
OUT = ROOT / "artifacts" / "synthetic"
INDOOR = ["Indoor Average Temperature", "Passenger Cabin Temperature Detected Value"]
SETPT = ["ACV Control Temperature (Cooling)", "Target Temperature Value"]
rng = np.random.default_rng(20260919)


# ------------------------------------------------------------------ ACV
def read_acv(name: str) -> pd.DataFrame:
    return pd.read_excel(SOURCE / "02_Datasets" / "ACV" / "Train" / name, engine="calamine")


def col(car: str, names: list[str], df: pd.DataFrame) -> str:
    return next(f"Car {car} - {n}" for n in names if f"Car {car} - {n}" in df.columns)


def swap_cars(df: pd.DataFrame, a: str, b: str) -> pd.DataFrame:
    out = df.copy()
    for c in df.columns:
        m = re.match(r"^Car (\d+) - (.+)$", c)
        if m and m.group(1) in (a, b):
            other = b if m.group(1) == a else a
            out[c] = df[f"Car {other} - {m.group(2)}"].to_numpy()
    return out


def acv_scenarios() -> list[dict]:
    """[{name, file, truth, note, expect}] with the files written to disk."""
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "acv").mkdir(exist_ok=True)
    labels = {r["filename"]: r["faulty_car"] for r in csv.DictReader(open(SOURCE / "02_Datasets/ACV/Train_Labels.csv"))}
    scenarios = []

    def emit(name, df, truth, note, expect="rank1", fmt="csv"):
        path = OUT / "acv" / f"{name}.{fmt}"
        if fmt == "csv":
            df.to_csv(path, index=False)
        else:
            df.to_excel(path, index=False)
        scenarios.append({"name": name, "path": path, "truth": truth, "note": note, "expect": expect})

    for base in ("acv_case_01", "acv_case_02", "acv_case_03", "acv_case_05", "acv_case_06"):
        df = read_acv(base + ".xlsx")
        t = labels[base + ".xlsx"]
        tag = base[-2:]
        # 1. leak moved to a different car id
        for dest in ("05", "08"):
            if dest != t:
                emit(f"{tag}_leak_moved_to_car{dest}", swap_cars(df, t, dest), dest, f"Leaking car relabelled {t}->{dest} by swapping column blocks.")
        ind_t = col(t, INDOOR, df); sp_t = col(t, SETPT, df)
        peers = [c for c in ("01", "02", "03", "04", "05", "06", "07", "08") if c != t]
        peer_gap = np.nanmean([(pd.to_numeric(df[col(c, INDOOR, df)], errors="coerce") - pd.to_numeric(df[col(c, SETPT, df)], errors="coerce")).mean() for c in peers])
        # 2. weaker leak: halve the faulty car's excess gap
        d2 = df.copy()
        valid = pd.to_numeric(d2[ind_t], errors="coerce") > 5
        excess = (pd.to_numeric(df[ind_t], errors="coerce") - pd.to_numeric(df[sp_t], errors="coerce"))[valid].mean() - peer_gap
        d2.loc[valid, ind_t] = pd.to_numeric(d2.loc[valid, ind_t]) - 0.5 * max(excess, 0)
        emit(f"{tag}_weaker_leak_half_excess", d2, t, "Faulty car's average excess gap halved.", "top3")
        # 3. sensor dropout on the faulty car (30% of samples read 0)
        d3 = df.copy(); mask = rng.random(len(d3)) < 0.3; d3.loc[mask, ind_t] = 0
        emit(f"{tag}_faulty_sensor_30pct_dropout", d3, t, "30% of the faulty car's indoor samples zeroed (sensor dropout).")
        # 4. dead sensor on a healthy car must not become the top pick
        healthy = next(c for c in ("07", "08", "06") if c != t)
        d4 = df.copy(); d4[col(healthy, INDOOR, d4)] = 0
        emit(f"{tag}_healthy_car{healthy}_dead_sensor", d4, t, f"Healthy car {healthy} has an all-zero indoor sensor.")
        # 5. measurement noise on every indoor reading
        d5 = df.copy()
        for c in ("01", "02", "03", "04", "05", "06", "07", "08"):
            k = col(c, INDOOR, d5); v = pd.to_numeric(d5[k], errors="coerce")
            d5[k] = np.where(v > 5, v + rng.normal(0, 0.4, len(d5)), v)
        emit(f"{tag}_indoor_noise_sd0.4C", d5, t, "Gaussian noise (sd 0.4 C) on all indoor temperatures.", "top3")
        # 6. only the first quarter of the recording
        emit(f"{tag}_first_quarter_only", df.iloc[: len(df) // 4].copy(), t, "Only the first 25% of rows are available.", "top3")
        # 7. six-car train (cars 07, 08 removed)
        keep = [c for c in df.columns if not re.match(r"^Car (07|08) - ", c)]
        if t not in ("07", "08"):
            emit(f"{tag}_six_car_train", df[keep].copy(), t, "Cars 07 and 08 removed from the file.")
        # 8. the other column-naming convention
        d8 = df.rename(columns={f"Car {c} - {INDOOR[0]}": f"Car {c} - {INDOOR[1]}" for c in ("01", "02", "03", "04", "05", "06", "07", "08")})
        d8 = d8.rename(columns={f"Car {c} - {SETPT[0]}": f"Car {c} - {SETPT[1]}" for c in ("01", "02", "03", "04", "05", "06", "07", "08")})
        emit(f"{tag}_alt_column_names", d8, t, "Columns renamed to the rich-file naming (cabin temperature / target temperature).")
        # 9. no fault at all: every car looks like a healthy peer
        d9 = df.copy(); d9[ind_t] = d9[col(peers[3], INDOOR, d9)].to_numpy(); d9[sp_t] = d9[col(peers[3], SETPT, d9)].to_numpy()
        emit(f"{tag}_no_fault_present", d9, None, "Faulty car replaced by a copy of a healthy peer: no true leak.", "low_confidence")
    # xlsx round trip on one small file
    df = read_acv("acv_case_06.xlsx")
    emit("06_xlsx_upload_roundtrip", df, labels["acv_case_06.xlsx"], "Same data re-saved as .xlsx to exercise the Excel path.", fmt="xlsx")
    return scenarios


def run_acv(client: httpx.Client, scenarios: list[dict]) -> list[dict]:
    rows = []
    for s in scenarios:
        with open(s["path"], "rb") as fh:
            r = client.post("/api/acv/analyze", files={"file": (s["path"].name, fh.read())}, timeout=180)
        if r.status_code != 200:
            rows.append({**s, "path": s["path"].name, "status": r.status_code, "error": r.json().get("detail")}); continue
        j = r.json(); rk = j["ranked_cars"]; n = len(rk)
        rank = rk.index(s["truth"]) + 1 if s["truth"] in rk else None
        if s["expect"] == "rank1":
            ok = rank == 1
        elif s["expect"] == "top3":
            ok = rank is not None and rank <= 3
        else:
            ok = j["confidence"] != "clear"
        rows.append({"name": s["name"], "note": s["note"], "expect": s["expect"], "truth": s["truth"], "ranked": "|".join(rk),
                     "rank_of_truth": rank, "score": None if rank is None else round((n - rank + 1) / n, 3),
                     "confidence": j["confidence"], "margin": j["top_margin"], "ok": ok, "ms": j["elapsed_ms"]})
    return rows


def acv_failure_cases(client: httpx.Client) -> list[dict]:
    """Bad input must give a clean 4xx JSON error, never a 500."""
    cases = {
        "not_a_spreadsheet": ("x.xlsx", b"hello world"),
        "wrong_extension": ("x.txt", b"a,b\n1,2\n"),
        "csv_without_car_columns": ("x.csv", b"Time,Temp\n1,20\n2,21\n"),
        "csv_cars_but_no_temperature": ("x.csv", b"Time,Car 01 - Foo,Car 02 - Foo\n1,1,1\n2,2,2\n"),
        "empty_file": ("x.csv", b""),
    }
    out = []
    for name, (fname, data) in cases.items():
        r = client.post("/api/acv/analyze", files={"file": (fname, data)})
        out.append({"name": name, "status": r.status_code, "ok": 400 <= r.status_code < 500 and "detail" in r.json(),
                    "code": r.json().get("detail", {}).get("code")})
    return out


# ------------------------------------------------------------------ Door
def tparse(s: str) -> float:
    y, mo, d, h, mi, se, ms = map(int, s.split("-"))
    return (datetime(y, mo, d, h, mi, se) + timedelta(milliseconds=ms)).timestamp()


def door_truth() -> pd.DataFrame:
    return pd.read_csv(SOURCE / "02_Datasets/Door/Train_Segments_Answer.csv")


def score_door(truth: list, pred: list) -> dict:
    def iou(a, b):
        i = max(0, min(a[1], b[1]) - max(a[0], b[0])); u = (a[1] - a[0]) + (b[1] - b[0]) - i
        return i / u if u > 0 else 0
    cand = sorted(((iou(g, p), i, j) for i, g in enumerate(truth) for j, p in enumerate(pred) if g[2] == p[2] and iou(g, p) > 0), reverse=True)
    ug, up, tot = set(), set(), 0.0
    for v, i, j in cand:
        if i in ug or j in up:
            continue
        ug.add(i); up.add(j); tot += v
    if not truth or not pred or tot == 0:
        return {"f1": 0.0, "recall": 0.0, "precision": 0.0, "true": len(truth), "pred": len(pred)}
    r, p = tot / len(truth), tot / len(pred)
    return {"f1": round(2 * r * p / (r + p), 4), "recall": round(r, 4), "precision": round(p, 4), "true": len(truth), "pred": len(pred)}


def door_scenarios() -> list[dict]:
    (OUT / "door").mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(SOURCE / "02_Datasets/Door/Train.csv")
    ans = door_truth()
    idx = {v: i for i, v in enumerate(df["Datetime"])}
    a_i = [(idx[s], idx[e]) for s, e in zip(ans.start_time, ans.end_time)]
    cur = "Motor current(mA)"; volt = "Motor Voltage(10mV)"
    scen = []

    def emit(name, frame, seg_ids, note):
        path = OUT / "door" / f"{name}.csv"
        frame.to_csv(path, index=False)
        truth = [(tparse(ans.start_time[i]), tparse(ans.end_time[i]), ans.status[i]) for i in seg_ids]
        scen.append({"name": name, "path": path, "truth": truth, "note": note})

    n = len(ans); half = n // 2
    everything = list(range(n))
    emit("first_half_of_stream", df.iloc[: a_i[half - 1][1] + 1].copy(), list(range(half)), "Only the first half of the recording.")
    emit("second_half_of_stream", df.iloc[a_i[half][0]:].copy(), list(range(half, n)), "Only the second half of the recording.")
    for scale in (0.85, 1.15):
        d = df.copy(); d[cur] = (d[cur] * scale).round().astype(int)
        emit(f"current_x{scale}", d, everything, f"Motor current scaled by {scale} (gain/calibration drift).")
    d = df.copy(); d[volt] = (d[volt] * 1.10).round().astype(int)
    emit("voltage_x1.10", d, everything, "Motor voltage +10%.")
    d = df.copy(); d[cur] = (d[cur] + rng.normal(0, 15, len(d))).round().clip(lower=0).astype(int)
    emit("current_noise_sd15mA", d, everything, "Gaussian noise (sd 15 mA) added to motor current.")
    ab = [i for i in everything if ans.status[i] != "Normal"][:12]
    keep = np.zeros(len(df), bool)
    for i in ab:
        keep[a_i[i][0]: a_i[i][1] + 1] = True
    emit("abnormal_only_stream", df[keep].copy(), ab, "Only 12 abnormal cycles (their rows), all with idle gaps between.")
    nm = [i for i in everything if ans.status[i] == "Normal"][:15]
    keep = np.zeros(len(df), bool)
    for i in nm:
        keep[a_i[i][0]: a_i[i][1] + 1] = True
    emit("normal_only_stream", df[keep].copy(), nm, "Only 15 normal cycles (a healthy-fleet day).")
    return scen


def run_door(client: httpx.Client, scenarios: list[dict]) -> list[dict]:
    rows = []
    for s in scenarios:
        with open(s["path"], "rb") as fh:
            r = client.post("/api/analyze", files={"file": (s["path"].name, fh.read())}, timeout=180)
        if r.status_code != 200:
            rows.append({"name": s["name"], "note": s["note"], "status": r.status_code, "error": r.json().get("detail"), "ok": False}); continue
        j = r.json()
        pred = [(tparse(c["start_time"]), tparse(c["end_time"]), c["prediction"]) for c in j["cycles"]]
        sc = score_door(s["truth"], pred)
        rows.append({"name": s["name"], "note": s["note"], **sc, "ok": sc["f1"] >= 0.9, "ms": j["elapsed_ms"]})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    args = ap.parse_args()
    client = httpx.Client(base_url=args.base, timeout=180)
    client.get("/api/health").raise_for_status()
    acv = run_acv(client, acv_scenarios())
    fails = acv_failure_cases(client)
    door = run_door(client, door_scenarios())
    report = {"base": args.base, "acv": acv, "acv_bad_input": fails, "door": door}
    (ROOT / "artifacts" / "synthetic-report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    n_ok = sum(r.get("ok", False) for r in acv)
    print(f"ACV scenarios: {n_ok}/{len(acv)} met expectation; mean score {np.mean([r['score'] for r in acv if r.get('score') is not None]):.3f}")
    for r in acv:
        if not r.get("ok"):
            print("  MISS", r.get("name"), "truth", r.get("truth"), "->", r.get("ranked"), "rank", r.get("rank_of_truth"), r.get("confidence"), r.get("error", ""))
    print(f"ACV bad-input handling: {sum(f['ok'] for f in fails)}/{len(fails)} clean 4xx")
    print(f"Door scenarios: {sum(r.get('ok', False) for r in door)}/{len(door)} with F1>=0.90")
    for r in door:
        print("  ", r["name"], {k: r.get(k) for k in ("f1", "true", "pred", "error")})


if __name__ == "__main__":
    sys.exit(main())
