"""Registry of the target tables the application offers. It identifies targets only;
their schema is always discovered from SQLite (see discovery.py)."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Target:
    target_id: str
    table_name: str
    display_name: str
    description: str
    database_type: str = "sqlite"

    def to_dict(self) -> dict:
        return asdict(self)


TARGETS: dict[str, Target] = {
    t.target_id: t
    for t in [Target("customer", "customer", "Customer", "Customer master data")]
}


def get_target(target_id: str) -> Target | None:
    return TARGETS.get(target_id)
