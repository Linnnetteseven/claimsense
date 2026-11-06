"""Apply the anchors status migration to the Oracle schema in the repo .env.

Run from the backend directory with that schema's Oracle settings in .env.
The script is intentionally not run automatically by the application.
"""
from __future__ import annotations

import os
from pathlib import Path

import oracledb
from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[1]


def _print_anchor_metadata(cursor) -> None:
    cursor.execute(
        """SELECT column_name, data_type, nullable, data_default
           FROM user_tab_columns
           WHERE table_name = 'ANCHORS'
           ORDER BY column_id"""
    )
    print("ANCHORS columns:")
    for row in cursor.fetchall():
        print(f"  {row[0]}: type={row[1]}, nullable={row[2]}, default={row[3]}")

    cursor.execute(
        """SELECT c.constraint_name, c.constraint_type, c.status,
                  LISTAGG(cc.column_name, ', ') WITHIN GROUP (ORDER BY cc.position)
           FROM user_constraints c
           LEFT JOIN user_cons_columns cc
             ON cc.constraint_name = c.constraint_name
            AND cc.table_name = c.table_name
           WHERE c.table_name = 'ANCHORS'
           GROUP BY c.constraint_name, c.constraint_type, c.status
           ORDER BY c.constraint_name"""
    )
    print("ANCHORS constraints:")
    for row in cursor.fetchall():
        print(f"  {row[0]}: type={row[1]}, status={row[2]}, columns={row[3] or '(check constraint)'}")

    cursor.execute("SELECT COUNT(*) FROM anchors")
    print("ANCHORS row count:", cursor.fetchone()[0])


def main() -> int:
    load_dotenv(REPO_ROOT / ".env")

    user = os.environ.get("ORACLE_USER", "").strip()
    password = os.environ.get("ORACLE_PASSWORD", "")
    dsn = os.environ.get("ORACLE_DSN", "").strip()
    wallet_dir = os.environ.get("ORACLE_WALLET_DIR", "").strip()
    if not all((user, password, dsn)):
        raise RuntimeError("Oracle configuration is incomplete; check ORACLE_USER, ORACLE_PASSWORD and ORACLE_DSN in .env")

    connect_options = {
        "user": user,
        "password": password,
        "dsn": dsn,
        "tcp_connect_timeout": 10,
    }
    if wallet_dir:
        wallet_path = Path(wallet_dir).expanduser().resolve()
        if not wallet_path.is_dir():
            raise RuntimeError("ORACLE_WALLET_DIR does not point to an available directory")
        connect_options.update(
            config_dir=str(wallet_path),
            wallet_location=str(wallet_path),
            wallet_password=os.environ.get("ORACLE_WALLET_PASSWORD") or None,
        )

    connection = oracledb.connect(**connect_options)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT USER FROM dual")
            print("connected as:", cursor.fetchone()[0])

            cursor.execute(
                """SELECT column_name FROM user_tab_columns
                   WHERE table_name = 'ANCHORS' AND column_name = 'STATUS'"""
            )
            if cursor.fetchone():
                print("STATUS already exists on ANCHORS; migration not run.")
            else:
                # This SQL file contains only the migration statements listed here.
                # Keep the Python runner explicit so it can report exactly what it applies.
                statements = (
                    """ALTER TABLE anchors ADD (
                           status VARCHAR2(16) DEFAULT 'confirmed' NOT NULL,
                           head_hash CHAR(64)
                       )""",
                    "ALTER TABLE anchors MODIFY (tx_hash NULL)",
                    """ALTER TABLE anchors ADD CONSTRAINT anchors_status_ck
                       CHECK (status IN ('pending', 'confirmed', 'failed'))""",
                    "ALTER TABLE anchors ADD CONSTRAINT anchors_root_hash_uq UNIQUE (root_hash)",
                )
                for statement in statements:
                    cursor.execute(statement)
                connection.commit()
                print("Anchors migration applied.")

            _print_anchor_metadata(cursor)
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
