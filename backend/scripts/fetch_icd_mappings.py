"""
Refresh the WHO ICD files in data/ from the WHO ICD-11 release server.

    python scripts/fetch_icd_mappings.py [RELEASE]     (default 2026-01)

Writes:
  data/icd11_mms.tsv          ICD-11 MMS codes and titles (from 11To10MapToOneCategory)
  data/icd10_to_icd11.tsv     WHO one-category map, ICD-10 code -> ICD-11 code
Source: https://icdcdn.who.int/static/releasefiles/<RELEASE>/mapping.zip
"""

import csv
import io
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
STEM = re.compile(r"^[1-9A-HJ-NP-Z][A-HJ-NP-Z][0-9][0-9A-HJ-NP-Z](\.[0-9A-HJ-NP-Z]{1,2})?$")


def main(release: str) -> int:
    url = f"https://icdcdn.who.int/static/releasefiles/{release}/mapping.zip"
    with urllib.request.urlopen(url, timeout=120) as resp:
        archive = zipfile.ZipFile(io.BytesIO(resp.read()))

    def rows(name):
        text = archive.read(name).decode("utf-8-sig")
        return csv.DictReader(io.StringIO(text), delimiter="\t")

    header = f"# Source: {url} (WHO ICD-11 release {release})\n"

    codes = {}
    for r in rows("11To10MapToOneCategory.txt"):
        code = (r["icd11Code"] or "").strip()
        if STEM.match(code):
            codes[code] = r["icd11Title"].strip().lstrip("- ").strip()
    with (DATA / "icd11_mms.tsv").open("w", encoding="utf-8") as fh:
        fh.write(header + "code\ttitle\n")
        fh.writelines(f"{c}\t{t}\n" for c, t in sorted(codes.items()))

    mapped = {}
    for r in rows("10To11MapToOneCategory.txt"):
        if r["10ClassKind"] in ("category", "modifiedcategory") and r["icd10Code"] and r["icd11Code"]:
            mapped[r["icd10Code"].strip()] = (r["icd11Code"].strip(), r["icd11Title"].strip().lstrip("- ").strip())
    with (DATA / "icd10_to_icd11.tsv").open("w", encoding="utf-8") as fh:
        fh.write(header + "icd10\ticd11\ticd11_title\n")
        fh.writelines(f"{k}\t{c}\t{t}\n" for k, (c, t) in sorted(mapped.items()))

    print(f"ICD-11 codes: {len(codes)}; ICD-10 -> ICD-11 mappings: {len(mapped)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "2026-01"))
