#!/usr/bin/env python3
"""Fetch ALL dashboard data server-side and save as reservoir-data.json.

Sources:
  - Lake Powell + Lake Mead elevations: USBR HDB
  - Streamflow (4 gauges, 30d daily + current): USGS NWIS
  - Snowpack (Grand Mesa SNOTEL): NRCS SNOTEL
"""
import urllib.request, json, ssl, datetime, os, csv, io

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "water-dashboard/1.0"})
    with urllib.request.urlopen(req, timeout=25, context=ctx) as r:
        return r.read().decode()

today = datetime.date.today().strftime('%m/%d/%Y')
start60 = (datetime.date.today() - datetime.timedelta(days=60)).strftime('%m/%d/%Y')
start30 = (datetime.date.today() - datetime.timedelta(days=30)).strftime('%m/%d/%Y')

result = {
    "updated": datetime.datetime.now(datetime.UTC).isoformat(),
    "powell": [],
    "mead": [],
    "usgs_iv": {},    # current instantaneous values per site
    "usgs_30d": [],   # 30-day daily values for Lees Ferry (09380000)
    "snotel_cur": None,
    "snotel_30d": [],
}

# ── Lake Powell (SVR=uchdb2, SDI=1928) ───────────────────────────────────────
try:
    r = get(f"https://www.usbr.gov/pn-bin/hdb/hdb.pl?svr=uchdb2&sdi=1928&tstp=DY&t1={start60}&t2={today}&table=R&mrid=0&format=json")
    for pt in json.loads(r).get("Series", [{}])[0].get("Data", []):
        if pt.get("v"):
            result["powell"].append({"d": pt["t"].split(" ")[0], "v": round(float(pt["v"]), 2)})
    print(f"Powell: {len(result['powell'])} days")
except Exception as e:
    print(f"Powell error: {e}")

# ── Lake Mead (SVR=lchdb, SDI=1930) ─────────────────────────────────────────
try:
    r2 = get(f"https://www.usbr.gov/pn-bin/hdb/hdb.pl?svr=lchdb&sdi=1930&tstp=DY&t1={start60}&t2={today}&table=R&mrid=0&format=json")
    for pt in json.loads(r2).get("Series", [{}])[0].get("Data", []):
        if pt.get("v"):
            result["mead"].append({"d": pt["t"].split(" ")[0], "v": round(float(pt["v"]), 2)})
    print(f"Mead: {len(result['mead'])} days")
except Exception as e:
    print(f"Mead error: {e}")

# ── USGS Instantaneous (current streamflow, 4 gauges) ───────────────────────
USGS_SITES = ["09380000", "09402500", "09163500", "09095500"]
try:
    sites_str = ",".join(USGS_SITES)
    r3 = get(f"https://waterservices.usgs.gov/nwis/iv/?format=json&parameterCd=00060&siteStatus=all&sites={sites_str}")
    d3 = json.loads(r3)
    for ts in d3.get("value", {}).get("timeSeries", []):
        site_id = ts["sourceInfo"]["siteCode"][0]["value"]
        values = ts.get("values", [{}])[0].get("value", [])
        if values:
            latest = values[-1]
            result["usgs_iv"][site_id] = {
                "value": float(latest["value"]) if latest["value"] != "-999999" else None,
                "dateTime": latest["dateTime"],
                "siteName": ts["sourceInfo"]["siteName"],
            }
    print(f"USGS IV: {len(result['usgs_iv'])} sites")
except Exception as e:
    print(f"USGS IV error: {e}")

# ── USGS 30-day daily (Lees Ferry 09380000) ──────────────────────────────────
try:
    r4 = get(f"https://waterservices.usgs.gov/nwis/dv/?format=json&parameterCd=00060&period=P30D&sites=09380000")
    d4 = json.loads(r4)
    for ts in d4.get("value", {}).get("timeSeries", []):
        for val in ts.get("values", [{}])[0].get("value", []):
            if val["value"] != "-999999":
                result["usgs_30d"].append({"d": val["dateTime"][:10], "v": float(val["value"])})
    print(f"USGS 30d: {len(result['usgs_30d'])} days")
except Exception as e:
    print(f"USGS 30d error: {e}")

# ── NRCS SNOTEL (Grand Mesa, 1040:CO:SNTL) ──────────────────────────────────
def parse_snotel_csv(text):
    """Parse SNOTEL CSV, return list of {d, v} dicts (skip header comment lines)."""
    rows = []
    reader = csv.reader(io.StringIO(text))
    for row in reader:
        if not row or row[0].startswith('#') or row[0].startswith('Date'):
            continue
        try:
            date_str = row[0].strip()
            val = row[1].strip()
            if val and val != '':
                rows.append({"d": date_str, "v": float(val)})
        except (IndexError, ValueError):
            continue
    return rows

try:
    snotel_cur_url = "https://wcc.sc.egov.usda.gov/reportGenerator/view_csv/customSingleStationReport/daily/start_of_period/1040:CO:SNTL/0,0/WTEQ::value?fitToScreen=false"
    text_cur = get(snotel_cur_url)
    rows_cur = parse_snotel_csv(text_cur)
    result["snotel_cur"] = rows_cur[-1]["v"] if rows_cur else None
    print(f"SNOTEL current: {result['snotel_cur']} in")
except Exception as e:
    print(f"SNOTEL current error: {e}")

try:
    snotel_hist_url = "https://wcc.sc.egov.usda.gov/reportGenerator/view_csv/customSingleStationReport/daily/start_of_period/1040:CO:SNTL/-30,0/WTEQ::value?fitToScreen=false"
    text_hist = get(snotel_hist_url)
    result["snotel_30d"] = parse_snotel_csv(text_hist)
    print(f"SNOTEL 30d: {len(result['snotel_30d'])} days")
except Exception as e:
    print(f"SNOTEL 30d error: {e}")

# ── Save ─────────────────────────────────────────────────────────────────────
outdir = os.path.dirname(os.path.abspath(__file__))
path = os.path.join(outdir, "reservoir-data.json")

has_data = result["powell"] or result["mead"] or result["usgs_iv"] or result["snotel_cur"]
if has_data:
    with open(path, "w") as f:
        json.dump(result, f)
    print(f"✓ Saved reservoir-data.json ({os.path.getsize(path)//1024}KB)")
else:
    print("No data fetched — keeping existing reservoir-data.json as fallback")
