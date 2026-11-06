import os, time
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
cur.execute("select count(*), max(seq) from audit_ledger")
print("ledger rows, max seq:", cur.fetchone())
cur.execute("select count(*) from anchors")
print("anchors:", cur.fetchone())
cur.execute("select * from anchors order by 1 desc fetch first 5 rows only")
print([d[0] for d in cur.description])
for r in cur.fetchall(): print(r)