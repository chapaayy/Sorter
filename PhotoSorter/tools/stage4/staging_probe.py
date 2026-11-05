"""Read-only, reproducible staging latency/disk/worker measurement.

No uploads, deletes, downloads, model jobs, migrations or container restart.
For external staging URLs an explicit --allow-remote-staging is required.
Never record session cookie values in report.
"""
from __future__ import annotations
import argparse
import concurrent.futures
import json
import math
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path

MAX_BODY=256*1024

def normalize_url(url,allow_remote=False):
    parsed=urllib.parse.urlsplit(url)
    if parsed.scheme not in ("http","https") or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("Expected http(s) staging URL with no credentials")
    if parsed.path not in ("","/") or parsed.query or parsed.fragment:
        raise ValueError("Use origin only, e.g. http://127.0.0.1:8000")
    local=parsed.hostname in ("localhost","127.0.0.1","::1")
    if not local and not allow_remote:
        raise ValueError("Remote probes require --allow-remote-staging, never use against live VPS")
    return parsed.scheme+"://"+parsed.netloc

def make_request(origin,path,*,cookie=None,timeout=7):
    headers={"User-Agent":"PhotoSorter-stage4-readonly/1","Cache-Control":"no-store"}
    if cookie:headers["Cookie"]=cookie
    req=urllib.request.Request(origin+path,headers=headers,method="GET")
    start=time.perf_counter()
    status=0
    data=b""
    try:
        with urllib.request.urlopen(req,timeout=timeout) as response:
            status=response.status
            data=response.read(MAX_BODY+1)
            if len(data)>MAX_BODY:raise ValueError("API response too large for probe")
    except urllib.error.HTTPError as err:
        status=err.code
    except (OSError,ValueError) as err:
        return {"status":0,"seconds":round(time.perf_counter()-start,6),
                "error":type(err).__name__}
    return {"status":status,"seconds":round(time.perf_counter()-start,6),
            "json":json.loads(data) if data and data.lstrip().startswith(b"{") else None}

def docker_sample():
    try:
        result=subprocess.run(["docker","stats","--no-stream","--format","{{json .}}"],
                   check=True,timeout=10,capture_output=True,text=True)
        rows=[json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        return [{"name":row.get("Name"),"cpu":row.get("CPUPerc"),
                 "memory":row.get("MemUsage"),"net_io":row.get("NetIO"),
                 "block_io":row.get("BlockIO")} for row in rows]
    except (OSError,subprocess.SubprocessError,ValueError):
        return None

def percentile(values,q):
    if not values:return None
    values=sorted(values)
    index=max(0,min(len(values)-1,math.ceil(q*len(values))-1))
    return round(values[index]*1000,2)

def collect(origin,count=100,concurrency=4,cookie=None,include_docker=False):
    if count<1 or count>3000 or concurrency<1 or concurrency>32:
        raise ValueError("Limit: 1..3000 requests and 1..32 concurrency")
    before=docker_sample() if include_docker else None
    started=time.monotonic()
    def check(_):
        return make_request(origin,"/api/health",timeout=7)
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        samples=list(pool.map(check,range(count)))
    elapsed=time.monotonic()-started
    codes=Counter(r["status"] for r in samples)
    successful=[r["seconds"] for r in samples if r["status"]==200]
    def optional(path):
        res=make_request(origin,path,cookie=cookie)
        if res["status"]!=200:
            return {"available":False,"status":res["status"]}
        return res.get("json")
    system=optional("/api/system/status") if cookie else {"available":False,"reason":"No cookie supplied"}
    storage=optional("/api/storage/usage") if cookie else {"available":False,"reason":"No cookie supplied"}
    return {
      "at":datetime.now(timezone.utc).isoformat(),"origin":origin,
      "requests":count,"concurrency":concurrency,
      "elapsed_seconds":round(elapsed,3),
      "requests_per_second":round(count/max(elapsed,.001),2),
      "status_codes":dict(sorted(codes.items())),
      "latency_ms":{"p50":percentile(successful,.5),"p95":percentile(successful,.95),
        "max":round(max(successful)*1000,2) if successful else None},
      "system":system,"storage":storage,
      "docker_before":before,"docker_after":docker_sample() if include_docker else None
    }

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url",required=True)
    p.add_argument("--count",type=int,default=100)
    p.add_argument("--concurrency",type=int,default=4)
    p.add_argument("--cookie-file",help="Read-only file containing a cookie header; never printed")
    p.add_argument("--docker-stats",action="store_true")
    p.add_argument("--allow-remote-staging",action="store_true")
    p.add_argument("--output",required=True,help="New JSON report file, existing files are not overwritten")
    args=p.parse_args(argv)
    origin=normalize_url(args.url,args.allow_remote_staging)
    cookie=None
    if args.cookie_file:
        raw=Path(args.cookie_file)
        if raw.stat().st_mode&0o077:raise ValueError("Cookie file must be owner-only (0600)")
        cookie=raw.read_text(encoding="utf8").strip()
        if "\n" in cookie or "\r" in cookie:raise ValueError("Invalid cookie header")
    report=collect(origin,args.count,args.concurrency,cookie,include_docker=args.docker_stats)
    output=Path(args.output)
    with output.open("x",encoding="utf8") as f:
        json.dump(report,f,ensure_ascii=False,indent=2)
    print(json.dumps({"output":str(output),"statuses":report["status_codes"],
                      "latency_ms":report["latency_ms"]},ensure_ascii=False))
    return 0 if report["status_codes"].get(200)==args.count else 1

if __name__=="__main__":sys.exit(main())
