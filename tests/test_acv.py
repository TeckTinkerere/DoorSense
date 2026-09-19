"""ACV localisation: synthetic frames with a known leaking car, plus API behaviour."""

from io import BytesIO
import zipfile

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from doorlens import acv
from doorlens.inference import InputError
from doorlens.main import create_app


def make_train(leak: str = "03", n: int = 600, cars=("01", "02", "03", "04", "05", "06", "07", "08"), seed: int = 1, leak_c: float = 1.0):
    rng = np.random.default_rng(seed)
    frame = {"Time": pd.date_range("2023-05-18", periods=n, freq="30s")}
    base = 24 + np.sin(np.linspace(0, 12, n))
    for car in cars:
        excess = leak_c if car == leak else 0.0
        frame[f"Car {car} - ACV Control Temperature (Cooling)"] = np.full(n, 24.0)
        frame[f"Car {car} - Indoor Average Temperature"] = base * 0 + 24 + 0.3 * np.sin(np.linspace(0, 12, n)) + excess + rng.normal(0, 0.15, n)
    return pd.DataFrame(frame)


def csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode()


def test_leaking_car_is_ranked_first_for_every_position():
    for leak in ("01", "04", "08"):
        result = acv.rank_cars(make_train(leak))
        assert result["ranked_cars"][0] == leak
        assert sorted(result["ranked_cars"]) == ["01", "02", "03", "04", "05", "06", "07", "08"]


def test_dead_sensor_car_is_ranked_last_not_first():
    df = make_train("03")
    df["Car 06 - Indoor Average Temperature"] = 0.0
    result = acv.rank_cars(df)
    assert result["ranked_cars"][0] == "03"
    assert result["ranked_cars"][-1] == "06"
    assert result["unscored_cars"] == ["06"]


def test_alternate_column_names_and_car_identifiers_are_preserved():
    df = make_train("02", cars=("01", "02", "03")).rename(columns=lambda c: c.replace("Indoor Average Temperature", "Passenger Cabin Temperature Detected Value").replace("ACV Control Temperature (Cooling)", "Target Temperature Value"))
    assert acv.rank_cars(df)["ranked_cars"][0] == "02"


def test_predictions_csv_matches_the_required_schema():
    data = acv.predictions_csv("acv_test_case.xlsx", ["03", "01", "02"])
    assert data.decode() == "file_id,ranked_cars\nacv_test_case.xlsx,03|01|02\n"


@pytest.mark.parametrize("content,name", [(b"not a workbook", "a.xlsx"), (b"a,b\n1,2\n", "a.txt"), (b"Time,x\n1,2\n", "a.csv"),
                                          (b"Time,Car 01 - Foo,Car 02 - Foo\n1,1,1\n", "a.csv"), (b"", "a.csv")])
def test_bad_input_is_a_clean_client_error(content, name):
    client = TestClient(create_app())
    response = client.post("/api/acv/analyze", files={"file": (name, content)})
    assert 400 <= response.status_code < 500
    assert {"code", "message"} <= response.json()["detail"].keys()


def test_api_round_trip_and_downloads():
    client = TestClient(create_app())
    data = csv_bytes(make_train("05"))
    result = client.post("/api/acv/analyze", files={"file": ("train.csv", data)}).json()
    assert result["ranked_cars"][0] == "05" and result["n_cars"] == 8
    downloaded = client.get(f"/api/acv/{result['id']}/predictions.csv")
    assert downloaded.content.decode().splitlines()[0] == "file_id,ranked_cars"
    assert downloaded.headers["content-disposition"].endswith('"acv_predictions.csv"')
    bundle = client.get("/api/submission.zip", params={"acv_id": result["id"]})
    assert zipfile.ZipFile(BytesIO(bundle.content)).namelist() == ["acv_predictions.csv"]
    assert client.get("/api/acv/acv-unknown/predictions.csv").status_code == 404
    assert client.get("/api/submission.zip").status_code == 422


def test_combined_zip_contains_both_subsystems_at_the_root():
    client = TestClient(create_app())
    door_source = None
    from pathlib import Path
    for candidate in (Path(__file__).resolve().parents[2] / "NebulaX-Hackathon-ProblemStatement/PS3/02_Datasets/Door/Test.csv",):
        if candidate.exists():
            door_source = candidate
    if door_source is None:
        pytest.skip("Door Test.csv not available")
    door = client.post("/api/analyze", files={"file": ("Test.csv", door_source.read_bytes())}).json()
    car = client.post("/api/acv/analyze", files={"file": ("t.csv", csv_bytes(make_train("02")))}).json()
    bundle = client.get("/api/submission.zip", params={"door": door["id"], "acv_id": car["id"]})
    assert sorted(zipfile.ZipFile(BytesIO(bundle.content)).namelist()) == ["acv_predictions.csv", "door_predictions.csv"]


def test_row_limit_is_enforced():
    with pytest.raises(InputError):
        acv.rank_cars(make_train(n=50), max_rows=10)
