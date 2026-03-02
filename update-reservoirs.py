#!/usr/bin/env python3
"""Fetch Lake Powell + Lake Mead elevation data from USBR HDB and save as JSON."""
import urllib.request, json, ssl, datetime, os

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "water-dashboard/1.0"})
    with urllib.request.urlopen(req, timeout=25, context=ctx) as r:
        return r.read().decode()

today = datetime.date.today().strftime('%m/%d/%Y')
start = (datetime.date.today() - datetime.timedelta(days=60)).strftime('%m/%d/%Y')

result = {"updated": datetime.datetime.now(datetime.UTC).isoformat(), "powell": [], "mead": []}

# Lake Powell (SVR=uchdb2, SDI=1928)
try:
    r = get(f"https://www.usbr.gov/pn-bin/hdb/hdb.pl?svr=uchdb2&sdi=1928&tstp=DY&t1={start}&t2={today}&table=R&mrid=0&format=json")
    for pt in json.loads(r).get("Series", [{}])[0].get("Data", []):
        if pt.get("v"):
            result["powell"].append({"d": pt["t"].split(" ")[0], "v": round(float(pt["v"]), 2)})
except Exception as e:
    print(f"Powell error: {e}")

# Lake Mead (SVR=lchdb, SDI=1930)
try:
    r2 = get(f"https://www.usbr.gov/pn-bin/hdb/hdb.pl?svr=lchdb&sdi=1930&tstp=DY&t1={start}&t2={today}&table=R&mrid=0&format=json")
    for pt in json.loads(r2).get("Series", [{}])[0].get("Data", []):
        if pt.get("v"):
            result["mead"].append({"d": pt["t"].split(" ")[0], "v": round(float(pt["v"]), 2)})
except Exception as e:
    print(f"Mead error: {e}")

outdir = os.path.dirname(os.path.abspath(__file__))
path = os.path.join(outdir, "reservoir-data.json")

# Only write if we got at least some data (fallback to existing file on full failure)
if result["powell"] or result["mead"]:
    with open(path, "w") as f:
        json.dump(result, f)
    print(f"Powell: {len(result['powell'])} days | Mead: {len(result['mead'])} days | Saved to {path}")
else:
    print("No data fetched — keeping existing reservoir-data.json as fallback")
