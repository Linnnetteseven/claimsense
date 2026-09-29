"""Loader for the SHA intervention catalogue (see the header of sha_interventions.csv)."""

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

_FIXTURE_PATH = Path(__file__).with_name("sha_interventions.csv")


@dataclass(frozen=True)
class Intervention:
    code: str
    description: str
    payment_mechanism: str
    levels: tuple[str, ...]            # facility levels where it may be billed, e.g. ("4", "5")
    level_tariffs: dict[str, float]    # official OCL tariffs by level, only where set
    preauth: tuple[str, ...]           # pre-authorization types required, e.g. ("surgical",)
    sample_tariff_kes: Optional[float]  # labelled sample, not official
    sample_tariff_source: str

    @property
    def requires_preauth(self) -> bool:
        return bool(self.preauth)

    def tariff_for(self, level: Optional[str]) -> tuple[Optional[float], str]:
        """(tariff, source) for a facility level: official OCL value first, then the sample."""
        if level and str(level) in self.level_tariffs:
            return self.level_tariffs[str(level)], f"OCL level {level} tariff"
        if self.sample_tariff_kes is not None:
            return self.sample_tariff_kes, "sample tariff"
        return None, ""


def _split(value: str) -> tuple[str, ...]:
    return tuple(v for v in value.split(";") if v)


@lru_cache(maxsize=1)
def interventions() -> dict[str, Intervention]:
    with _FIXTURE_PATH.open(encoding="utf-8") as fh:
        rows = csv.DictReader(line for line in fh if not line.startswith("#"))
        return {
            row["code"]: Intervention(
                code=row["code"],
                description=row["description"],
                payment_mechanism=row["payment_mechanism"],
                levels=_split(row["levels"]),
                level_tariffs={
                    str(level): float(row[f"tariff_l{level}"])
                    for level in range(2, 7)
                    if row[f"tariff_l{level}"]
                },
                preauth=_split(row["preauth"]),
                sample_tariff_kes=float(row["sample_tariff_kes"]) if row["sample_tariff_kes"] else None,
                sample_tariff_source=row["sample_tariff_source"],
            )
            for row in rows
        }


def get_intervention(code: str) -> Optional[Intervention]:
    return interventions().get(str(code).strip().upper())
