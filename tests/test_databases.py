"""Multiple SQLite databases: GET /api/databases, database_id on targets and runs (CONTRACT.md "Databases")."""

import sqlite3
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from src.api.main import app, get_database_catalog, get_run_store, get_target_db
from src.runs.store import RunStore
from src.target.catalog import DatabaseCatalog
from src.target.database import CUSTOMER_SEED, ORDERS_SEED, initialize_database, initialize_demo_databases

client = TestClient(app)

ORDERS_HEADER = "order_id,customer_email,amount,currency,status,order_date\n"


@pytest.fixture
def folder(tmp_path):
    """A database folder with the demo databases, a user-added database and files that are not databases."""
    directory = tmp_path / "databases"
    initialize_demo_databases(directory)
    with closing(sqlite3.connect(directory / "hr.sqlite")) as conn, conn:
        conn.execute("CREATE TABLE staff (staff_id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    (directory / "notes.db").write_text("not a database")
    (directory / "readme.txt").write_text("ignored")
    default = directory / "crm.db"
    runs = RunStore()
    app.dependency_overrides[get_target_db] = lambda: str(default)
    app.dependency_overrides[get_database_catalog] = lambda: DatabaseCatalog(directory, default, seed_demo=False)
    app.dependency_overrides[get_run_store] = lambda: runs
    yield directory
    app.dependency_overrides.clear()


def count(path, table):
    with closing(sqlite3.connect(path)) as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def upload(content, target_id, database_id=None, name="data.csv"):
    data = {"target_id": target_id, **({"database_id": database_id} if database_id is not None else {})}
    return client.post("/api/runs", data=data, files={"file": (name, content.encode(), "text/csv")})


# --- GET /api/databases -------------------------------------------------------------------------

def test_lists_sqlite_files_default_first(folder):
    r = client.get("/api/databases")
    assert r.status_code == 200
    assert r.json() == {"databases": [
        {"database_id": "crm", "display_name": "CRM", "file_name": "crm.db", "database_type": "sqlite",
         "table_count": 1, "is_default": True},
        {"database_id": "hr", "display_name": "Hr", "file_name": "hr.sqlite", "database_type": "sqlite",
         "table_count": 1, "is_default": False},
        {"database_id": "sales", "display_name": "Sales", "file_name": "sales.db", "database_type": "sqlite",
         "table_count": 2, "is_default": False},
    ]}


def test_default_database_outside_the_folder_is_listed(tmp_path):
    directory, default = tmp_path / "dbs", tmp_path / "elsewhere" / "main.db"
    directory.mkdir()
    initialize_database(default)
    ids = [d.database_id for d in DatabaseCatalog(directory, default, seed_demo=False).databases()]
    assert ids == ["main"]


def test_same_name_different_extension_gets_distinct_ids(tmp_path):
    directory = tmp_path / "dbs"
    initialize_database(directory / "a.db")
    initialize_database(directory / "a.sqlite")
    ids = [d.database_id for d in DatabaseCatalog(directory, directory / "a.db", seed_demo=False).databases()]
    assert ids == ["a", "a_sqlite"]


# --- targets per database ----------------------------------------------------------------------

def test_targets_are_the_tables_of_the_chosen_database(folder):
    body = client.get("/api/targets", params={"database_id": "sales"}).json()
    assert body == {"targets": [
        {"target_id": "orders", "table_name": "orders", "display_name": "Orders", "description": "Customer orders",
         "database_type": "sqlite", "database_id": "sales"},
        {"target_id": "products", "table_name": "products", "display_name": "Products",
         "description": "Product catalog", "database_type": "sqlite", "database_id": "sales"},
    ]}
    # A table without a known description has none, rather than an invented one.
    assert client.get("/api/targets", params={"database_id": "hr"}).json()["targets"] == [
        {"target_id": "staff", "table_name": "staff", "display_name": "Staff", "database_type": "sqlite",
         "database_id": "hr"}]


def test_omitting_database_id_uses_the_default_database(folder):
    assert [t["target_id"] for t in client.get("/api/targets").json()["targets"]] == ["customer"]
    assert client.get("/api/targets/customer").json()["database_id"] == "crm"


def test_target_schema_in_a_chosen_database(folder):
    body = client.get("/api/targets/orders", params={"database_id": "sales"}).json()
    assert (body["target_id"], body["database_id"]) == ("orders", "sales")
    assert [c["name"] for c in body["columns"]] == ["order_id", "customer_email", "amount", "currency", "status",
                                                    "order_date"]
    check = next(c for c in body["constraints"] if c["type"] == "CHECK" and c["columns"] == ["currency"])
    assert check["allowed_values"] == ["USD", "EUR", "INR"]


@pytest.mark.parametrize("database_id", ["nope", "../crm", "crm.db", "/etc/passwd", "notes"])
def test_unknown_database_is_404(folder, database_id):
    r = client.get("/api/targets", params={"database_id": database_id})
    assert r.status_code == 404
    assert r.json() == {"detail": {"code": "database_not_found",
                                   "message": f"Database '{database_id}' was not found.", "field": "database_id"}}


def test_table_from_another_database_is_target_not_found(folder):
    r = client.get("/api/targets/customer", params={"database_id": "sales"})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "target_not_found"


# --- runs in a chosen database -----------------------------------------------------------------

def test_run_loads_into_the_chosen_database_only(folder):
    good = ORDERS_HEADER + "6001,dan@example.com,19.5,USD,PLACED,2024-04-01\n6002,eve@example.com,5,INR,SHIPPED,2024-04-02\n"
    r = upload(good, "orders", "sales")
    assert r.status_code == 201, r.text
    body = r.json()
    assert (body["status"], body["database_id"], body["target_id"]) == ("SUCCEEDED", "sales", "orders")
    assert body["load_result"] == {"rows_loaded": 2, "target_table": "orders"}
    assert count(folder / "sales.db", "orders") == len(ORDERS_SEED) + 2
    assert count(folder / "crm.db", "customer") == len(CUSTOMER_SEED)


def test_run_without_database_id_uses_the_default_database(folder):
    body = upload("customer_id,name,email\n3001,Zed,zed@example.com\n", "customer").json()
    assert (body["status"], body["database_id"]) == ("SUCCEEDED", "crm")
    assert count(folder / "crm.db", "customer") == len(CUSTOMER_SEED) + 1


def test_run_errors_for_unknown_database_or_table(folder):
    assert upload("x\n1\n", "orders", "nope").json()["detail"]["code"] == "database_not_found"
    assert upload("x\n1\n", "customer", "sales").json()["detail"]["code"] == "target_not_found"


def test_retry_stays_in_the_parent_database(folder):
    bad = ORDERS_HEADER + "6001,dan@example.com,19.5,GBP,PLACED,2024-04-01\n"
    parent = upload(bad, "orders", "sales").json()
    assert (parent["status"], parent["database_id"]) == ("FAILED_VALIDATION", "sales")
    fixed = ORDERS_HEADER + "6001,dan@example.com,19.5,USD,PLACED,2024-04-01\n"
    r = client.post(f"/api/runs/{parent['run_id']}/retry", files={"file": ("fixed.csv", fixed.encode(), "text/csv")})
    assert r.status_code == 201, r.text
    child = r.json()
    assert (child["status"], child["database_id"], child["parent_run_id"]) == ("SUCCEEDED", "sales", parent["run_id"])
    assert count(folder / "sales.db", "orders") == len(ORDERS_SEED) + 1
