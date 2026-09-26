"""Phase 1 uploads: POST /api/runs and GET /api/runs/{run_id} (docs/implementation/CONTRACT.md)."""

import csv
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.runs import ingest
from src.runs.store import RunStore, get_run_store

DATA = Path(__file__).resolve().parents[1] / "data"
SOURCE = (DATA / "source_customers.csv").read_bytes()
TARGET = (DATA / "target_customers.csv").read_bytes()
RUN_LOG = (DATA / "pipeline_run.json").read_bytes()
GOOD = b"id,email\n1,a@x.com\n2,b@x.com\n"

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_store():
    """Each test gets its own empty store."""
    store = RunStore()
    app.dependency_overrides[get_run_store] = lambda: store
    yield store
    app.dependency_overrides.pop(get_run_store, None)


def upload(source=SOURCE, target=TARGET, run_log=None, source_name="source_customers.csv",
           target_name="target_customers.csv"):
    files = {"source_file": (source_name, source, "text/csv"), "target_file": (target_name, target, "text/csv")}
    if run_log is not None:
        files["pipeline_run_file"] = ("pipeline_run.json", run_log, "application/json")
    return client.post("/api/runs", files=files)


def error(r, status, code, field):
    assert r.status_code == status, r.text
    detail = r.json()["detail"]
    assert set(detail) == {"code", "message", "field"}
    assert detail["code"] == code and detail["field"] == field
    assert detail["message"].startswith(field)  # a plain sentence naming the file
    return detail["message"]


# --- success ----------------------------------------------------------------------------------

def test_upload_demo_files_returns_run_summary():
    r = upload()
    assert r.status_code == 201, r.text
    body = r.json()
    assert set(body) == {"run_id", "created_at", "source", "target", "pipeline_run"}
    assert re.fullmatch(r"run_[0-9a-f]{12}", body["run_id"])
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", body["created_at"])
    assert body["pipeline_run"] is None

    src, tgt = body["source"], body["target"]
    assert (src["file_name"], src["row_count"]) == ("source_customers.csv", 20)
    assert (tgt["file_name"], tgt["row_count"]) == ("target_customers.csv", 23)
    for ds, raw in ((src, SOURCE), (tgt, TARGET)):
        header = next(csv.reader(raw.decode().splitlines()))
        assert [c["name"] for c in ds["columns"]] == header  # file order
        assert set(ds["columns"][0]) == {"name", "non_null_count", "sample_values"}


def test_preview_is_first_20_rows_in_file_order_with_every_column():
    body = upload().json()
    tgt = body["target"]
    rows = list(csv.DictReader(TARGET.decode().splitlines()))
    assert len(tgt["preview"]) == 20
    assert [p["customer_id"] for p in tgt["preview"]] == [r["customer_id"] for r in rows[:20]]
    assert all(list(p) == [c["name"] for c in tgt["columns"]] for p in tgt["preview"])


def test_target_customer_id_null_count_and_null_outside_preview():
    tgt = upload().json()["target"]
    cid = next(c for c in tgt["columns"] if c["name"] == "customer_id")
    assert cid["non_null_count"] == 22  # the one empty cell is on row 23, outside the preview
    assert all(p["customer_id"] is not None for p in tgt["preview"])


def test_empty_cell_is_null_in_preview():
    body = upload(source=b"id,email,status\n1,,active\n2,b@x.com,\n", target=GOOD).json()
    assert body["source"]["preview"] == [
        {"id": "1", "email": None, "status": "active"},
        {"id": "2", "email": "b@x.com", "status": None},
    ]
    email = body["source"]["columns"][1]
    assert email == {"name": "email", "non_null_count": 1, "sample_values": ["b@x.com"]}


def test_sample_values_are_up_to_3_distinct_in_first_appearance_order():
    body = upload().json()
    for ds in (body["source"], body["target"]):
        for col in ds["columns"]:
            assert len(col["sample_values"]) <= 3
            assert len(set(col["sample_values"])) == len(col["sample_values"])
    status = next(c for c in body["source"]["columns"] if c["name"] == "status")
    assert status["sample_values"] == ["active", "inactive", "churned"]  # order of first appearance


def test_upload_with_run_log_returns_it():
    body = upload(run_log=RUN_LOG).json()
    assert body["pipeline_run"] == json.loads(RUN_LOG)


def test_empty_optional_run_log_part_is_treated_as_not_provided():
    files = {"source_file": ("s.csv", GOOD, "text/csv"), "target_file": ("t.csv", GOOD, "text/csv"),
             "pipeline_run_file": ("", b"", "application/octet-stream")}
    r = client.post("/api/runs", files=files)
    assert r.status_code == 201 and r.json()["pipeline_run"] is None


def test_get_run_returns_same_body():
    created = upload(run_log=RUN_LOG).json()
    r = client.get(f"/api/runs/{created['run_id']}")
    assert r.status_code == 200 and r.json() == created


def test_na_strings_stay_text_and_bom_is_stripped():
    source = "\ufeffid,region,note\n1,NA,null\n2,None,\n".encode("utf-8")
    body = upload(source=source, target=GOOD).json()
    assert [c["name"] for c in body["source"]["columns"]] == ["id", "region", "note"]
    assert body["source"]["preview"][0] == {"id": "1", "region": "NA", "note": "null"}
    assert body["source"]["preview"][1] == {"id": "2", "region": "None", "note": None}


def test_header_names_are_trimmed():
    body = upload(source=b" id , email \n1,a@x.com\n", target=GOOD).json()
    assert [c["name"] for c in body["source"]["columns"]] == ["id", "email"]


def test_store_keeps_full_dataframes(fresh_store):
    body = upload().json()
    record = fresh_store.get(body["run_id"])
    assert len(record.source) == 20 and len(record.target) == 23  # not just the preview


# --- errors -----------------------------------------------------------------------------------

def test_unknown_run_id_is_404():
    r = client.get("/api/runs/run_000000000000")
    assert r.status_code == 404
    assert r.json() == {"detail": {
        "code": "run_not_found",
        "message": "Run run_000000000000 was not found. It may have expired; upload the files again.",
        "field": None}}


def test_file_too_large(monkeypatch):
    monkeypatch.setattr(ingest, "MAX_CSV_BYTES", 100)
    msg = error(upload(source=GOOD, target=b"id\n" + b"1\n" * 100), 413, "file_too_large", "target_file")
    assert "100 bytes" in msg


def test_run_log_too_large(monkeypatch):
    monkeypatch.setattr(ingest, "MAX_RUN_LOG_BYTES", 10)
    error(upload(source=GOOD, target=GOOD, run_log=RUN_LOG), 413, "file_too_large", "pipeline_run_file")


def test_too_many_rows(monkeypatch):
    monkeypatch.setattr(ingest, "MAX_CSV_ROWS", 20)
    msg = error(upload(), 422, "too_many_rows", "target_file")  # source has 20 rows: OK; target 23
    assert msg == "target_file has 23 data rows; the limit is 20."


def test_invalid_encoding():
    error(upload(source="id,name\n1,café\n".encode("latin-1")), 422, "invalid_encoding", "source_file")


@pytest.mark.parametrize("bad", [b"", b"   \n", b"id,email\n", b"id,email\n\n\n"])
def test_invalid_csv_empty_or_no_data_rows(bad):
    error(upload(source=bad), 422, "invalid_csv", "source_file")


@pytest.mark.parametrize("bad", [b"a,b\n1,2,3\n4,5,6\n", b"a,b\n1,2\n3,4,5\n", b'a,b\n"unclosed,1\n'])
def test_invalid_csv_unparseable(bad):
    error(upload(target=bad), 422, "invalid_csv", "target_file")


def test_invalid_header_duplicate():
    msg = error(upload(source=b"id,email, email\n1,a,b\n"), 422, "invalid_header", "source_file")
    assert msg == "source_file has 2 columns named 'email'. Column names must be unique."


@pytest.mark.parametrize("bad", [b"id,,email\n1,2,3\n", b"id,email,\n1,2,3\n", b"id, ,email\n1,2,3\n"])
def test_invalid_header_empty_name(bad):
    error(upload(source=bad), 422, "invalid_header", "source_file")


@pytest.mark.parametrize("bad", [b"{not json", b"[1, 2]", b'"text"', b'{"steps": "x"}',
                                 b'{"steps": [{"rows_in": 1}]}', b'{"steps": [{"name": 5}]}',
                                 b'{"logs": "line"}', b'{"logs": ["ok", 3]}', b'{"x": NaN}'])
def test_invalid_pipeline_run(bad):
    error(upload(source=GOOD, target=GOOD, run_log=bad), 422, "invalid_pipeline_run", "pipeline_run_file")


def test_minimal_run_log_fields_are_optional():
    body = upload(source=GOOD, target=GOOD, run_log=b'{"steps": null, "custom": {"k": 1}}').json()
    assert body["pipeline_run"] == {"steps": None, "custom": {"k": 1}}


def test_first_bad_file_in_contract_order_is_reported():
    r = upload(source=b"", target=b"x".join([b"\xff"] * 3), run_log=b"[")
    error(r, 422, "invalid_csv", "source_file")
    r = upload(source=GOOD, target=b"", run_log=b"[")
    error(r, 422, "invalid_csv", "target_file")


def test_missing_target_file_is_default_422():
    r = client.post("/api/runs", files={"source_file": ("s.csv", GOOD, "text/csv")})
    assert r.status_code == 422 and isinstance(r.json()["detail"], list)


def test_21st_run_evicts_the_oldest():
    ids = [upload(source=GOOD, target=GOOD).json()["run_id"] for _ in range(21)]
    assert len(set(ids)) == 21
    assert client.get(f"/api/runs/{ids[0]}").status_code == 404
    assert client.get(f"/api/runs/{ids[1]}").status_code == 200
    assert client.get(f"/api/runs/{ids[-1]}").status_code == 200


def test_failed_upload_stores_nothing(fresh_store):
    upload(source=b"")
    assert fresh_store._runs == {}
