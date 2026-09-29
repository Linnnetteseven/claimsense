"""Loader for the SHA intervention catalogue (see the header of sha_interventions.csv)."""

import csv
import re
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
    access_point: str = ""             # "OP", "IP", "OP and IP"
    gender: str = "ALL"                # "ALL", "FEMALE", "MALE"
    min_age: Optional[int] = None
    max_age: Optional[int] = None
    diagnoses_raw: str = ""            # OCL diagnosis list, see diagnosis_matches()

    def allowed_at_level(self, level: str) -> bool:
        """True if billable at the facility level ("4" also matches OCL sub-levels 4A, 4B...)."""
        if not self.levels:
            return True
        base = str(level).strip().upper()[:1]
        return any(l.upper().startswith(base) for l in self.levels)

    def diagnosis_matches(self, code: str) -> Optional[bool]:
        """None if the intervention has no diagnosis restriction, else whether the ICD-11 code is listed."""
        allowed = _parse_diagnoses(self.diagnoses_raw)
        if allowed is None:
            return None
        stem = re.split(r"[&/]", str(code).strip().upper())[0]
        for start, end in allowed:
            if end is None and stem.startswith(start):
                return True
            if end is not None and start <= stem <= end:
                return True
        return False

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


@lru_cache(maxsize=4096)
def _parse_diagnoses(raw: str) -> Optional[tuple[tuple[str, Optional[str]], ...]]:
    """
    OCL diagnosis lists mix single codes, ranges ("QB95.0-QB95.Z", "BA00.0 - BA2Z") and
    free text ("Universal (exclude global exclusions)"). Returns (start, end-or-None) pairs,
    or None when any diagnosis is allowed. ICD-11 never uses I or O, so OCL typos such as
    JBOA are read as JB0A.
    """
    if not raw or "universal" in raw.lower():
        return None
    text = re.sub(r"\s*-\s*", "-", raw.upper())
    out = []
    for token in re.split(r"[;,\s]+", text):
        token = token.strip().replace("O", "0").replace("I", "1")
        if not token:
            continue
        start, _, end = token.partition("-")
        out.append((start, end or None))
    return tuple(out) or None


def _int(value: str) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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
                access_point=row["access_point"],
                gender=row["gender"] or "ALL",
                min_age=_int(row["min_age"]),
                max_age=_int(row["max_age"]),
                diagnoses_raw=row["diagnoses"],
            )
            for row in rows
        }


def get_intervention(code: str) -> Optional[Intervention]:
    return interventions().get(str(code).strip().upper())
