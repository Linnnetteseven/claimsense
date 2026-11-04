"""Guarded, experimental Oracle Select AI over aggregate views only."""
from __future__ import annotations

import re

from .select_ai_connection import get_select_ai_pool

PROFILE = "HAKIKI_ANALYTICS_READONLY"
ALLOWED_VIEWS = {
    "V_CLAIMS_BY_STATUS", "V_SCORE_BY_DEPARTMENT", "V_TOP_FAILED_RULES",
    "V_REWORK_TREND_WEEKLY", "V_LEDGER_STATUS", "V_SIGNOFF_PROGRESS",
    "V_MANAGEMENT_KPIS",
}
FORBIDDEN_SQL = re.compile(
    r"\b(insert|update|delete|merge|drop|alter|create|grant|revoke|truncate|commit|rollback|execute|call|begin|declare|into|pivot|unpivot|model|xmltable|json_table)\b|--|/\*|\*/|;",
    re.IGNORECASE,
)
TABLE_REF = re.compile(
    r"\b(?:from|join)\s+(?:(?:\"?([A-Z0-9_$#]+)\"?)\s*\.\s*)?\"?([A-Z0-9_$#]+)\"?",
    re.IGNORECASE,
)


class SelectAINotAvailable(RuntimeError):
    """Select AI, its profile, or the optional database configuration is unavailable."""


def validate_generated_select(sql: str) -> str:
    statement = str(sql or "").strip()
    if len(statement) > 8000 or not re.match(r"^select\b", statement, re.IGNORECASE):
        raise ValueError("Only a single SELECT over approved analytics views is allowed")
    if FORBIDDEN_SQL.search(statement):
        raise ValueError("Generated SQL contains a forbidden operation")
    from_clause = re.search(r"\bfrom\b(.*?)(?:\bwhere\b|\bgroup\s+by\b|\border\s+by\b|\bhaving\b|$)", statement, re.IGNORECASE | re.DOTALL)
    if not from_clause or "," in from_clause.group(1) or re.search(r"\b(apply|lateral)\b", from_clause.group(1), re.IGNORECASE):
        raise ValueError("Generated SQL contains an unapproved relation expression")
    references = TABLE_REF.findall(statement)
    if not references:
        raise ValueError("Generated SQL must read an approved analytics view")
    for owner, name in references:
        if name.strip('"').upper() not in ALLOWED_VIEWS:
            raise ValueError("Generated SQL referenced an unapproved database object")
        if owner and owner.strip('"').upper() != "HAKIKI_APP":
            raise ValueError("Generated SQL referenced an unapproved schema")
    return statement


def run_readonly_analytics_query(prompt: str) -> dict:
    """Ask Select AI for SQL, guard the SQL, and execute as a view-only user."""
    if not prompt or len(prompt) > 500:
        raise ValueError("Question must be between 1 and 500 characters")
    try:
        with get_select_ai_pool().acquire() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT DBMS_CLOUD_AI.GENERATE(
                              prompt => :prompt,
                              profile_name => 'HAKIKI_ANALYTICS_READONLY',
                              action => 'showsql') FROM dual""",
                    {"prompt": prompt}, fetch_lobs=False,
                )
                generated = cursor.fetchone()
                if not generated:
                    raise SelectAINotAvailable()
                sql = validate_generated_select(generated[0])
                cursor.arraysize = 100
                cursor.execute(sql)
                columns = [column[0].lower() for column in cursor.description]
                rows = []
                for row in cursor.fetchmany(100):
                    rows.append({key: (value.isoformat() if hasattr(value, "isoformat") else value)
                                 for key, value in zip(columns, row)})
        return {"available": True, "sql": sql, "columns": columns, "rows": rows,
                "row_limit": 100, "profile": PROFILE}
    except ValueError:
        raise
    except Exception as exc:
        raise SelectAINotAvailable(type(exc).__name__) from None
