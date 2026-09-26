"""Deterministic validation tools. Each returns a ValidationResult; none use the LLM."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

import pandas as pd

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
MAX_EXAMPLES = 10


@dataclass
class ValidationResult:
    check: str
    passed: bool
    summary: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _ids(series: pd.Series) -> pd.Series:
    """Normalise ids to stripped strings; blanks become NA."""
    s = series.astype("string").str.strip()
    return s.mask(s == "")


def record_count_comparison(source: pd.DataFrame, target: pd.DataFrame) -> ValidationResult:
    src, tgt = len(source), len(target)
    return ValidationResult(
        check="record_count_comparison",
        passed=src == tgt,
        summary=f"source={src} rows, target={tgt} rows, difference={tgt - src:+d}",
        details={"source_count": src, "target_count": tgt, "difference": tgt - src},
    )


def null_customer_id_check(target: pd.DataFrame, id_col: str = "customer_id") -> ValidationResult:
    nulls = target[_ids(target[id_col]).isna()]
    return ValidationResult(
        check="null_customer_id_check",
        passed=nulls.empty,
        summary=f"{len(nulls)} target row(s) have a null {id_col}",
        details={"null_count": len(nulls), "rows": nulls.head(MAX_EXAMPLES).astype(object).where(nulls.notna(), None).to_dict("records")},
    )


def duplicate_customer_id_check(target: pd.DataFrame, id_col: str = "customer_id") -> ValidationResult:
    ids = _ids(target[id_col]).dropna()
    counts = ids.value_counts()
    dupes = counts[counts > 1].sort_index()
    return ValidationResult(
        check="duplicate_customer_id_check",
        passed=dupes.empty,
        summary=f"{len(dupes)} customer_id(s) appear more than once ({int((dupes - 1).sum())} extra row(s))",
        details={
            "duplicate_id_count": len(dupes),
            "extra_rows": int((dupes - 1).sum()),
            "duplicates": {str(k): int(v) for k, v in dupes.items()},
        },
    )


def missing_target_records(source: pd.DataFrame, target: pd.DataFrame, id_col: str = "customer_id") -> ValidationResult:
    src_ids = _ids(source[id_col])
    tgt_ids = set(_ids(target[id_col]).dropna())
    missing = source[~src_ids.isin(tgt_ids)]
    return ValidationResult(
        check="missing_target_records",
        passed=missing.empty,
        summary=f"{len(missing)} source record(s) not found in target",
        details={"missing_count": len(missing), "missing_records": missing.head(MAX_EXAMPLES).to_dict("records")},
    )


def invalid_email_check(df: pd.DataFrame, email_col: str = "email", label: str = "target") -> ValidationResult:
    emails = df[email_col].astype("string")
    bad = df[~emails.fillna("").str.match(EMAIL_RE)]
    return ValidationResult(
        check=f"invalid_email_check[{label}]",
        passed=bad.empty,
        summary=f"{len(bad)} {label} row(s) have an invalid email",
        details={"invalid_count": len(bad), "rows": bad.head(MAX_EXAMPLES).astype(object).where(bad.notna(), None).to_dict("records")},
    )


def invalid_status_check(df: pd.DataFrame, allowed: tuple[str, ...], status_col: str = "status",
                         label: str = "target") -> ValidationResult:
    """Exact match against the allowed set (case-sensitive); null/blank status is invalid."""
    status = df[status_col].astype("string").str.strip()
    bad = df[~status.isin(list(allowed)).fillna(False)]
    return ValidationResult(
        check=f"invalid_status_check[{label}]",
        passed=bad.empty,
        summary=f"{len(bad)} {label} row(s) have a status outside {list(allowed)}",
        details={
            "invalid_count": len(bad),
            "allowed": list(allowed),
            "invalid_values": {str(k): int(v) for k, v in
                               bad[status_col].astype(object).fillna("<null>").astype(str).value_counts().sort_index().items()},
            "rows": bad.head(MAX_EXAMPLES).astype(object).where(bad.notna(), None).to_dict("records"),
        },
    )


def run_all_validations(source: pd.DataFrame, target: pd.DataFrame) -> list[ValidationResult]:
    checks: list[Callable[[], ValidationResult]] = [
        lambda: record_count_comparison(source, target),
        lambda: null_customer_id_check(target),
        lambda: duplicate_customer_id_check(target),
        lambda: missing_target_records(source, target),
        lambda: invalid_email_check(source, label="source"),
        lambda: invalid_email_check(target, label="target"),
    ]
    return [c() for c in checks]
