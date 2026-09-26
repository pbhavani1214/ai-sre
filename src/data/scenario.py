"""Synthetic customer pipeline scenario with deliberately injected failures.

The pipeline (simulated) does:
    extract  -> read source_customers.csv
    transform-> cast customer_id to integer, lowercase emails,
                INNER JOIN with a country->region lookup
    load     -> write to target in batches of 5 (with retry on timeout)

Injected failures (NOT exposed to the AI - it must discover them from evidence):
    1. Region lookup is missing country "SG"; the inner join silently drops
       Singapore customers.
    2. Load batch 3 timed out after partially committing; the retry reloaded
       the whole batch without idempotency -> duplicate customer_ids.
    3. A legacy source id ("CUST-1020") fails integer coercion -> null
       customer_id in target.
    4. One source email is malformed and passes through unvalidated.

Running this module regenerates the files in data/ deterministically.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
SOURCE_FILE = DATA_DIR / "source_customers.csv"
TARGET_FILE = DATA_DIR / "target_customers.csv"
RUN_FILE = DATA_DIR / "pipeline_run.json"

PIPELINE_DESCRIPTION = (
    "Nightly customer sync pipeline. Extracts customers from the CRM export "
    "(source_customers.csv), casts customer_id to integer, lowercases emails, "
    "enriches each customer with a sales region via an INNER JOIN on a "
    "country->region lookup table, and loads the result into the warehouse "
    "table (target_customers.csv) in batches of 5 rows. Failed batches are "
    "retried once. Expected contract: every source customer appears exactly "
    "once in target with a non-null customer_id and a valid email."
)

REGION_LOOKUP = {"US": "NA", "CA": "NA", "GB": "EMEA", "DE": "EMEA", "IN": "APAC", "AU": "APAC"}

_SOURCE_ROWS = [
    ("1001", "Alice Carter", "Alice.Carter@example.com", "US", "2024-01-05"),
    ("1002", "Bob Singh", "bob.singh@example.com", "IN", "2024-01-09"),
    ("1003", "Chloe Martin", "chloe.martin@example.com", "GB", "2024-01-12"),
    ("1004", "Daniel Tan", "daniel.tan@example.com", "SG", "2024-01-15"),
    ("1005", "Eva Schmidt", "eva.schmidt@example.com", "DE", "2024-01-20"),
    ("1006", "Farah Khan", "farah.khan@example.com", "IN", "2024-02-02"),
    ("1007", "George Brown", "george.brown@example", "US", "2024-02-07"),
    ("1008", "Hannah Lee", "hannah.lee@example.com", "AU", "2024-02-11"),
    ("1009", "Ivan Petrov", "ivan.petrov@example.com", "DE", "2024-02-18"),
    ("1010", "Julia Rossi", "julia.rossi@example.com", "GB", "2024-02-25"),
    ("1011", "Kevin Wong", "kevin.wong@example.com", "CA", "2024-03-01"),
    ("1012", "Laura Chen", "laura.chen@example.com", "US", "2024-03-04"),
    ("1013", "Mohan Rao", "mohan.rao@example.com", "IN", "2024-03-08"),
    ("1014", "Nina Lim", "nina.lim@example.com", "SG", "2024-03-10"),
    ("1015", "Oscar Diaz", "oscar.diaz@example.com", "US", "2024-03-15"),
    ("1016", "Priya Nair", "priya.nair@example.com", "IN", "2024-03-19"),
    ("1017", "Quinn Taylor", "quinn.taylor@example.com", "AU", "2024-03-22"),
    ("1018", "Rosa Alvarez", "rosa.alvarez@example.com", "CA", "2024-03-27"),
    ("1019", "Sam Okafor", "sam.okafor@example.com", "GB", "2024-04-01"),
    ("CUST-1020", "Tara Novak", "tara.novak@example.com", "DE", "2024-04-03"),
]

COLUMNS = ["customer_id", "name", "email", "country", "signup_date"]


def build_source() -> pd.DataFrame:
    return pd.DataFrame(_SOURCE_ROWS, columns=COLUMNS)


def simulate_pipeline(source: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Run the buggy pipeline and return (target_df, pipeline_run_metadata)."""
    df = source.copy()
    df["customer_id"] = pd.to_numeric(df["customer_id"], errors="coerce").astype("Int64")
    coerced = int(df["customer_id"].isna().sum())
    df["email"] = df["email"].str.lower()

    lookup = pd.DataFrame(list(REGION_LOOKUP.items()), columns=["country", "region"])
    joined = df.merge(lookup, on="country", how="inner")  # bug: should be left join

    batches = [joined.iloc[i : i + 5] for i in range(0, len(joined), 5)]
    loaded = []
    for i, batch in enumerate(batches, start=1):
        loaded.append(batch)
        if i == 3:  # bug: batch 3 committed, then timed out and was retried in full
            loaded.append(batch)
    target = pd.concat(loaded, ignore_index=True)

    run = {
        "run_id": "run-2024-04-05-0200",
        "pipeline": "customer_nightly_sync",
        "started_at": "2024-04-05T02:00:00Z",
        "finished_at": "2024-04-05T02:03:41Z",
        "status": "SUCCESS",
        "config": {
            "source": "data/source_customers.csv",
            "target": "data/target_customers.csv",
            "batch_size": 5,
            "max_retries": 1,
            "join": {"table": "region_lookup", "on": "country", "how": "inner"},
            "region_lookup_countries": sorted(REGION_LOOKUP),
        },
        "steps": [
            {"name": "extract", "status": "SUCCESS", "rows_in": len(source), "rows_out": len(source)},
            {
                "name": "transform.cast_customer_id",
                "status": "SUCCESS",
                "rows_in": len(source),
                "rows_out": len(df),
                "warnings": [f"{coerced} value(s) could not be parsed as integer and were set to null"],
            },
            {"name": "transform.lowercase_email", "status": "SUCCESS", "rows_in": len(df), "rows_out": len(df)},
            {
                "name": "transform.join_region_lookup",
                "status": "SUCCESS",
                "rows_in": len(df),
                "rows_out": len(joined),
            },
            {
                "name": "load",
                "status": "SUCCESS",
                "rows_in": len(joined),
                "rows_written": len(target),
                "batches": len(batches),
            },
        ],
        "logs": [
            "02:00:00 INFO  extract: read 20 rows from source_customers.csv",
            f"02:00:02 WARN  cast_customer_id: {coerced} value(s) coerced to null",
            "02:00:03 INFO  lowercase_email: done",
            f"02:00:04 INFO  join_region_lookup: {len(df)} rows in, {len(joined)} rows out",
            "02:01:10 INFO  load: batch 1/4 committed (5 rows)",
            "02:01:40 INFO  load: batch 2/4 committed (5 rows)",
            "02:02:15 ERROR load: batch 3/4 timeout after 30s waiting for commit ack",
            "02:02:16 INFO  load: retrying batch 3/4 (attempt 2/2)",
            "02:02:50 INFO  load: batch 3/4 committed (5 rows)",
            "02:03:40 INFO  load: batch 4/4 committed (3 rows)",
            f"02:03:41 INFO  run finished: status=SUCCESS rows_written={len(target)}",
        ],
    }
    return target, run


def generate(data_dir: Path = DATA_DIR) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    source = build_source()
    target, run = simulate_pipeline(source)
    source.to_csv(data_dir / SOURCE_FILE.name, index=False)
    target.to_csv(data_dir / TARGET_FILE.name, index=False)
    (data_dir / RUN_FILE.name).write_text(json.dumps(run, indent=2), encoding="utf-8")


def load_scenario(data_dir: Path = DATA_DIR) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Load (source_df, target_df, pipeline_run) from disk. IDs are read as strings."""
    source = pd.read_csv(data_dir / SOURCE_FILE.name, dtype={"customer_id": str}, keep_default_na=False, na_values=[""])
    target = pd.read_csv(data_dir / TARGET_FILE.name, dtype={"customer_id": str}, keep_default_na=False, na_values=[""])
    run = json.loads((data_dir / RUN_FILE.name).read_text(encoding="utf-8"))
    return source, target, run


if __name__ == "__main__":
    generate()
    print(f"Scenario written to {DATA_DIR}")
