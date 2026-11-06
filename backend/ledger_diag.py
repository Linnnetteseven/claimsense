import os, sys, re, time
from dotenv import load_dotenv
import oracledb

load_dotenv(r"..\.env")
dsn = os.environ["ORACLE_DSN"]
if len(sys.argv) > 1:  # e.g. python ledger_diag.py high
    dsn = re.sub(r"_(low|medium|high|tp|tpurgent)(?=[.)]|$)", "_" + sys.argv[1], dsn)
kw = dict(user=os.environ["ORACLE_USER"], password=os.environ["ORACLE_PASSWORD"],
          dsn=dsn, tcp_connect_timeout=10)
wd = os.environ.get("ORACLE_WALLET_DIR")
if wd:
    kw.update(config_dir=wd, wallet_location=wd,
              wallet_password=os.environ.get("ORACLE_WALLET_PASSWORD"))
oracledb.defaults.fetch_lobs = False
t0 = time.time()
c = oracledb.connect(**kw)
c.call_timeout = 30000
print(f"connected {time.time()-t0:.1f}s (service: {sys.argv[1] if len(sys.argv) > 1 else 'as in .env'})", flush=True)
cur = c.cursor(); cur.arraysize = 500

def step(name, sql, fetch="all"):
    t = time.time()
    try:
        cur.execute(sql)
        rows = cur.fetchall() if fetch == "all" else cur.fetchmany(50)
        print(f"{name}: {time.time()-t:.1f}s, rows={len(rows)}", flush=True)
        return rows
    except Exception as e:
        print(f"{name}: FAILED after {time.time()-t:.1f}s -> {str(e)[:120]}", flush=True)

step("1 count ledger", "select count(*) from audit_ledger")
step("2 count details", "select count(*) from audit_event_details")
r = step("3 clob size", "select max(dbms_lob.getlength(details_json)), avg(dbms_lob.getlength(details_json)) from audit_event_details")
if r: print("   max/avg clob length:", r[0], flush=True)
step("4 ledger only", "select seq from audit_ledger")
step("5 details keys only", "select event_seq from audit_event_details")
step("6 join, no clob", "select l.seq, d.event_seq from audit_ledger l left join audit_event_details d on d.event_seq = l.seq")
step("8 ALL details as text", "select event_seq, dbms_lob.substr(details_json, 4000, 1) from audit_event_details")
print("done", flush=True)