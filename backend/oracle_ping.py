import os, time, socket
from dotenv import load_dotenv
import oracledb

load_dotenv(r"..\.env")  # repo-root .env

host = "adb.af-johannesburg-1.oraclecloud.com"
t = time.time()
try:
    print("DNS:", socket.gethostbyname(host), f"{time.time()-t:.1f}s")
except Exception as e:
    print("DNS FAILED:", e, f"{time.time()-t:.1f}s")

kw = dict(user=os.environ["ORACLE_USER"], password=os.environ["ORACLE_PASSWORD"],
          dsn=os.environ["ORACLE_DSN"], tcp_connect_timeout=10)
wd = os.environ.get("ORACLE_WALLET_DIR")
if wd:
    kw.update(config_dir=wd, wallet_location=wd,
              wallet_password=os.environ.get("ORACLE_WALLET_PASSWORD"))
t = time.time()
c = oracledb.connect(**kw)
print("connected in", f"{time.time()-t:.1f}s")
cur = c.cursor()
cur.execute("select count(*) from claims")
print("claims:", cur.fetchone())
t = time.time()
for _ in range(10):
    cur.execute("select 1 from dual"); cur.fetchone()
print("avg per query:", round((time.time()-t)/10*1000), "ms")