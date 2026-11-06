import os
from dotenv import load_dotenv
import oracledb

load_dotenv(r"..\.env")
kw = dict(user=os.environ["ORACLE_USER"], password=os.environ["ORACLE_PASSWORD"],
          dsn=os.environ["ORACLE_DSN"], tcp_connect_timeout=10)
wd = os.environ.get("ORACLE_WALLET_DIR")
if wd:
    kw.update(config_dir=wd, wallet_location=wd,
              wallet_password=os.environ.get("ORACLE_WALLET_PASSWORD"))
c = oracledb.connect(**kw); cur = c.cursor()
cur.execute("select user from dual"); print("connected as:", cur.fetchone()[0])
for t in ("VALIDATION_RUNS", "ANCHORS"):
    cur.execute("select column_name, data_type, nullable from user_tab_columns where table_name=:t order by column_id", t=t)
    print(f"\n{t}:")
    for r in cur.fetchall(): print("  ", r)
cur.execute("""select c.constraint_name, c.constraint_type, cc.column_name
               from user_constraints c
               join user_cons_columns cc on cc.constraint_name = c.constraint_name
               where c.table_name = 'ANCHORS'""")
print("\nANCHORS constraints:")
for r in cur.fetchall(): print("  ", r)
cur.execute("select count(*) from anchors"); print("\nanchor rows:", cur.fetchone()[0])