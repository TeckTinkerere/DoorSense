"""Protect official exports and the original/probe HTTP boundary."""

import asyncio
import csv
from io import BytesIO, StringIO
import socket
import zipfile

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException

from doorlens.api.routes import analyze
from doorlens.inference import COLUMNS, I, P, PROBES, V
from doorlens.main import create_app
from doorlens.services.settings import Settings
from doorlens.services.store import AnalysisStore


def recording_bytes(count=60, *, two_cycles=False):
    """A complete synthetic opening, used for API contracts, not accuracy."""
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(COLUMNS)
    for block in range(2 if two_cycles else 1):
        for index in range(count):
            milliseconds = index * 20
            second, millisecond = divmod(milliseconds, 1000)
            row = {name: 0 for name in COLUMNS}
            row.update({"Datetime": f"2025-1-2-3-4-{second + block * 10}-{millisecond}",
                        I: 1100 + index, V: 2400, "Motor electrodynamic force": 90 + index,
                        P: index * 100 / (count - 1), "Door is opening": 1,
                        "Open command": 1, "DCSR": int(index == 0), "DCSL": int(index == 0),
                        "Door Opened": int(index == count - 1)})
            writer.writerow([row[name] for name in COLUMNS])
    return stream.getvalue().encode()


class CountingFrozenModel:
    """A deterministic injected inference double; never fits anything."""
    def __init__(self, identifier):
        self.model_id = identifier
        self.metadata = {"model_label": identifier}
        self.calls = 0

    def predict(self, cycle):
        self.calls += 1
        score = float(np.clip((cycle[I].mean() - 900) / 400, 0, 1))
        return {"prediction": "Abnormal resistance" if score >= .5 else "Normal", "score": score,
                "direction": "Open" if cycle[P].iloc[-1] > cycle[P].iloc[0] else "Close"}

    def reference(self, cycle):
        return {"progress": [.25, .75], "current_median_a": [1.0, 1.0],
                "current_lower_a": [.8, .8], "current_upper_a": [1.2, 1.2],
                "sample_count": 2, "provenance": "Synthetic API test fixture"}


@pytest.fixture
def harness(tmp_path):
    now = [1_800_000_000.0]
    store = AnalysisStore(max_count=2, ttl_seconds=60, clock=lambda: now[0])
    models = {"final": CountingFrozenModel("test-final"), "demo-fold-0": CountingFrozenModel("test-fold-0")}
    settings = Settings(model_directory=tmp_path / "models", frontend_directory=tmp_path / "frontend")
    app = create_app(settings, store, models)
    with TestClient(app) as client:
        yield client, app, now, models


def upload(client, content=None):
    return client.post("/api/analyze", files={"file": ("recording.csv", content if content is not None else recording_bytes(), "text/csv")})


def test_upload_inspect_and_exact_exports(harness):
    client, _, _, models = harness
    content = recording_bytes(two_cycles=True)
    response = upload(client, content)
    assert response.status_code == 200, response.text
    run = response.json()
    assert run["context"] == "upload" and run["model_id"] == "test-final"
    assert run["summary"] == {"cycle_count": 2, "normal_count": 0, "abnormal_count": 2}
    assert run["overview"]["time_ms"].count(None) == 1
    assert run["overview"]["current_a"].count(None) == 1
    selected = client.get(f'/api/analyses/{run["id"]}/cycles/0').json()
    assert selected["cycle"] == run["cycles"][0]
    assert len(selected["trace"]["time_ms"]) == 60
    assert selected["trace"]["time_ms"][1] - selected["trace"]["time_ms"][0] == 20
    csv_response = client.get(f'/api/analyses/{run["id"]}/predictions.csv')
    assert csv_response.headers["content-disposition"] == 'attachment; filename="door_predictions.csv"'
    assert csv_response.content.splitlines()[0] == b"start_time,end_time,prediction"
    exported = list(csv.DictReader(StringIO(csv_response.text)))
    assert exported == [{key: row[key] for key in ("start_time", "end_time", "prediction")} for row in run["cycles"]]
    assert exported[0]["start_time"] == "2025-1-2-3-4-0-0"
    archive_response = client.get(f'/api/analyses/{run["id"]}/predictions.zip')
    with zipfile.ZipFile(BytesIO(archive_response.content)) as archive:
        assert archive.namelist() == ["door_predictions.csv"]
        assert archive.read("door_predictions.csv") == csv_response.content
    assert models["final"].calls == 2  # inspection and download never reclassify
    assert response.headers["cache-control"] == "no-store"


def test_all_five_probes_are_real_copies_and_exports_stay_identical(harness):
    client, app, _, models = harness
    run = upload(client).json()
    base = f'/api/analyses/{run["id"]}'
    original = app.state.analysis_store.get(run["id"])
    before_frame = original.cycles[0].copy(deep=True)
    before_csv = client.get(base + "/predictions.csv").content
    before_zip = client.get(base + "/predictions.zip").content
    before_trace = client.get(base + "/cycles/0").json()["trace"]
    for probe in PROBES:
        response = client.post(base + "/cycles/0/challenge", json={"probe_id": probe["id"]})
        assert response.status_code == 200, response.text
        changed = response.json()
        assert changed["original"] == {"prediction": run["cycles"][0]["prediction"], "score": run["cycles"][0]["score"]}
        assert changed["label_changed"] == (changed["original"]["prediction"] != changed["altered"]["prediction"])
        assert changed["synthetic"] is True and changed["original_csv_sha256"] == run["csv_sha256"]
        trace = changed["trace"]
        if probe["id"].startswith("current"):
            gain = .95 if "minus" in probe["id"] else 1.05
            assert trace["current_a"] == pytest.approx(np.asarray(before_trace["current_a"]) * gain)
            assert trace["voltage_v"] == before_trace["voltage_v"]
        elif probe["id"].startswith("voltage"):
            gain = .95 if "minus" in probe["id"] else 1.05
            assert trace["voltage_v"] == pytest.approx(np.asarray(before_trace["voltage_v"]) * gain)
            assert trace["current_a"] == before_trace["current_a"]
        else:
            keep = [i for i in range(60) if i not in (20, 40)]
            assert changed["sample_count"] == 58
            for field in before_trace:
                assert trace[field] == [before_trace[field][i] for i in keep]
        pd.testing.assert_frame_equal(original.cycles[0], before_frame)
        assert client.get(base + "/predictions.csv").content == before_csv
        assert client.get(base + "/predictions.zip").content == before_zip
    assert models["final"].calls == 6


@pytest.mark.parametrize("content,code", [(b"", "empty_file"), (b"a,b\n1,2\n", "missing_columns"),
    (recording_bytes().replace(b"1100", b"inf", 1), "non_finite"),
    (recording_bytes().replace(b"2025-1-2-3-4-0-20", b"2025-1-2-3-4-0-0", 1), "timestamp_order"),
    (recording_bytes(count=5), "incomplete_cycle")])
def test_invalid_content_has_actionable_json(harness, content, code):
    response = upload(harness[0], content)
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == code
    assert response.json()["detail"]["message"]
    assert len(harness[1].state.analysis_store) == 0


def test_actual_read_upload_limit_and_row_limit(tmp_path):
    models = {"final": CountingFrozenModel("test-final")}
    settings = Settings(max_upload_bytes=256, frontend_directory=tmp_path)
    with TestClient(create_app(settings, models=models)) as client:
        response = upload(client, b"x" * 257)
        assert response.status_code == 413
        assert response.json()["detail"]["code"] == "upload_too_large"
    settings = Settings(max_rows=50, frontend_directory=tmp_path)
    with TestClient(create_app(settings, models=models)) as client:
        response = upload(client)
        assert response.status_code == 422 and response.json()["detail"]["code"] == "row_limit"
    assert models["final"].calls == 0


def test_oversize_read_stops_at_limit_and_closes_upload(harness):
    class TrackedUpload:
        filename = "large.csv"
        consumed = 0
        closed = False

        async def read(self, count):
            self.consumed += count
            return b"x" * count

        async def close(self):
            self.closed = True

    service = harness[1].state.analysis_service
    service.settings = Settings(max_upload_bytes=100)
    file = TrackedUpload()
    with pytest.raises(HTTPException) as caught:
        asyncio.run(analyze(file=file, service=service))
    assert caught.value.status_code == 413
    assert file.consumed == 101 and file.closed


def test_unknown_expired_deleted_and_count_eviction(harness):
    client, app, now, _ = harness
    missing = client.get("/api/analyses/no-such-run/predictions.csv")
    assert missing.status_code == 404
    malformed = client.get("/api/analyses/" + "a" * 32 + "." + "é" * 32 + "/predictions.csv")
    assert malformed.status_code == 404
    run = upload(client).json()
    now[0] += 60
    expired = client.get(f'/api/analyses/{run["id"]}/predictions.csv')
    assert expired.status_code == 410 and expired.json()["detail"]["code"] == "analysis_expired"
    assert len(app.state.analysis_store) == 0
    runs = [upload(client).json() for _ in range(3)]
    assert len(app.state.analysis_store) == 2
    assert client.get(f'/api/analyses/{runs[0]["id"]}/predictions.zip').status_code == 410
    assert client.get(f'/api/analyses/{runs[1]["id"]}/predictions.zip').status_code == 200
    assert client.delete(f'/api/analyses/{runs[2]["id"]}').status_code == 204
    assert client.get(f'/api/analyses/{runs[2]["id"]}/predictions.csv').status_code == 410
    # No unbounded expired-ID/tombstone collection is required.
    assert len(app.state.analysis_store) == 1


def test_bad_requests_and_unknown_api_never_fall_through_html(harness, tmp_path):
    client = harness[0]
    run = upload(client).json()
    for index in ("-1", "1"):
        response = client.get(f'/api/analyses/{run["id"]}/cycles/{index}')
        assert response.status_code == 404 and response.json()["detail"]["code"] == "cycle_not_found"
    assert client.post("/api/analyze").status_code == 422
    assert client.post(f'/api/analyses/{run["id"]}/cycles/0/challenge', json={"probe_id": "unknown"}).status_code == 422
    assert client.post(f'/api/analyses/{run["id"]}/cycles/0/challenge', json={"probe_id": PROBES[0]["id"], "override": True}).status_code == 422
    (tmp_path / "index.html").write_text("<html>STATIC FRONTEND</html>")
    (tmp_path / "404.html").write_text("<html>STATIC NOT FOUND</html>")
    with TestClient(create_app(Settings(frontend_directory=tmp_path), models={})) as static:
        assert "STATIC FRONTEND" in static.get("/").text
        for path in ("/api", "/api/unknown", "/api/nested/unknown"):
            for method in ("get", "post", "put", "delete", "patch"):
                response = getattr(static, method)(path)
                assert response.status_code == 404
                assert response.json()["detail"]["code"] == "api_not_found"
                assert "text/html" not in response.headers["content-type"]


def test_bundled_demo_model_identity_and_current_minus_reproduction():
    """Uses the real packaged fold model, never a forced label or canned score."""
    with TestClient(create_app()) as client:
        response = client.post("/api/demo")
        assert response.status_code == 200, response.text
        run = response.json()
        assert run["context"] == "development-demo"
        assert run["cycles"][0]["cycle_id"] == "train_seg_017"
        health = client.get("/api/health").json()
        assert run["model_id"] == health["demo_model_id"] != health["model_id"]
        assert run["cycles"][0]["prediction"] == "Abnormal resistance"
        assert run["cycles"][0]["score"] == pytest.approx(.6369046416612815, abs=1e-9)
        result = client.post(f'/api/analyses/{run["id"]}/cycles/0/challenge', json={"probe_id": "current_minus_5pct"}).json()
        assert result["altered"]["prediction"] == "Normal"
        assert result["altered"]["score"] == pytest.approx(.3600240212649819, abs=1e-9)
        assert result["label_changed"] is True


def test_runtime_core_does_not_require_external_connection(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Core application must not initiate a network connection")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    with TestClient(create_app()) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/methodology").status_code == 200
        run = client.post("/api/demo").json()
        assert client.get(f'/api/analyses/{run["id"]}/predictions.zip').status_code == 200


def test_unexpected_inference_failure_is_json_and_retains_no_partial_run(harness):
    _, app, _, models = harness

    def failed(cycle):
        raise RuntimeError("private internal failure detail")

    models["final"].predict = failed
    with TestClient(app, raise_server_exceptions=False) as client:
        response = upload(client)
        assert response.status_code == 500
        assert response.json()["detail"]["code"] == "internal_error"
        assert "private internal" not in response.text
        assert len(app.state.analysis_store) == 0
