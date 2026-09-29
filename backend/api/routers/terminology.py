"""Code search for the claim form: ICD-11 (offline WHO release) and SHA interventions (MOH OCL)."""

from fastapi import APIRouter, Query

from data.sha_tariffs import interventions
from terminology import icd11

router = APIRouter(prefix="/terminology", tags=["terminology"])


@router.get("/icd11")
def search_icd11(q: str = Query("", max_length=80), limit: int = Query(10, ge=1, le=25)) -> list[dict]:
    """ICD-11 MMS codes by code prefix or title words; an ICD-10 code returns its WHO mapping first."""
    results = []
    mapped = icd11.from_icd10(q) if icd11.looks_like_icd10(q) else None
    if mapped:
        results.append({"code": mapped[0], "title": mapped[1], "note": f"WHO map from ICD-10 {q.strip().upper()}"})
    for code, title in icd11.lookup_codes(q, limit):
        if not any(r["code"] == code for r in results):
            results.append({"code": code, "title": title})
    return results[:limit]


@router.get("/interventions")
def search_interventions(
    q: str = Query("", max_length=80), level: str = "", limit: int = Query(10, ge=1, le=25)
) -> list[dict]:
    """SHA intervention codes by code prefix or description words, optionally only those billable at a level."""
    needle = q.strip().upper()
    if not needle:
        return []
    words = [w for w in needle.split() if len(w) > 2]
    hits = []
    for info in interventions().values():
        if level and not info.allowed_at_level(level):
            continue
        desc = info.description.upper()
        if info.code.startswith(needle):
            rank = 0
        elif words and all(w in desc for w in words):
            rank = 1
        else:
            continue
        hits.append((rank, info.code, info))
    hits.sort(key=lambda h: (h[0], h[1]))
    return [
        {"code": i.code, "title": i.description, "payment": i.payment_mechanism.lower(),
         "levels": list(i.levels), "preauth": list(i.preauth)}
        for _, _, i in hits[:limit]
    ]
