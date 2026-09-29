"""Loader for the SHA intervention code fixture (see sha_tariffs_sample.csv header)."""

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

_FIXTURE_PATH = Path(__file__).with_name("sha_tariffs_sample.csv")


@dataclass(frozen=True)
class Intervention:
    code: str
    description: str
    tariff_kes: Optional[float]      # None when no sourced sample value exists
    requires_preauth: Optional[bool]  # None when unknown
    tariff_source: str


@lru_cache(maxsize=1)
def interventions() -> dict[str, Intervention]:
    with _FIXTURE_PATH.open(encoding="utf-8") as fh:
        rows = csv.DictReader(line for line in fh if not line.startswith("#"))
        return {
            row["code"]: Intervention(
                code=row["code"],
                description=row["description"],
                tariff_kes=float(row["tariff_kes"]) if row["tariff_kes"] else None,
                requires_preauth={"true": True, "false": False}.get(row["requires_preauth"]),
                tariff_source=row["tariff_source"],
            )
            for row in rows
        }


def get_intervention(code: str) -> Optional[Intervention]:
    return interventions().get(str(code).strip().upper())
