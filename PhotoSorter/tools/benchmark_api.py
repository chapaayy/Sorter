"""Repeatable read-only API latency sampler. Run only against approved staging."""
from __future__ import annotations
import argparse,json,statistics,time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone

def percentile(values,p):
    data=sorted(values)
    if not data:return None
    return round(data[max(0,int(len(data)*p+.9999)-1)]*1000,2)

def measure(url,cookie=""):
    request=urllib.request.Request(url,headers={"Cookie":cookie} if cookie else {})
    start=time.perf_counter()
    with urllib.request.urlopen(request,timeout=15) as reply:
        reply.read()
        if reply.status!=200:raise ValueError(f"HTTP {reply.status}")
    return time.perf_counter()-start

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--url",required=True,help="Approved staging URL /api/health")
    parser.add_argument("--count",type=int,default=100)
    parser.add_argument("--concurrency",type=int,default=4)
    parser.add_argument("--cookie",default="",help="Optional authorized cookie (not saved)")
    args=parser.parse_args()
    if not 1<=args.count<=10000 or not 1<=args.concurrency<=16:
        parser.error("count=1..10000 concurrency=1..16")
    good=[];errors=[]
    began=time.monotonic()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures=[pool.submit(measure,args.url,args.cookie) for _ in range(args.count)]
        for future in futures:
            try:good.append(future.result())
            except Exception as exc:errors.append(type(exc).__name__)
    print(json.dumps({"at":datetime.now(timezone.utc).isoformat(),
        "url":args.url,"requests":args.count,"completed":len(good),
        "errors":errors[:20],"p50_ms":percentile(good,.5),
        "p95_ms":percentile(good,.95),"max_ms":percentile(good,1.),
        "wall_seconds":round(time.monotonic()-began,3)},indent=2))

if __name__=="__main__":main()
