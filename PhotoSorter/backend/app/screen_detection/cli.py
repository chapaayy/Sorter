"""Manual stage-2 CPU test; no background scheduler, no MegaLoc or ZIP changes."""
from __future__ import annotations
import argparse
import json
import sys
from .xfeat_assets import install,status

def main(argv=None):
    parser=argparse.ArgumentParser(description="Verified XFeat CPU screen detection")
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--install",action="store_true",help="fetch pinned model and source")
    group.add_argument("--verify",action="store_true",help="verify model files offline")
    group.add_argument("--prune-cache",action="store_true",help="prune obsolete descriptors older than 7 days")
    group.add_argument("--run-id",help="analyze a completed MegaLoc run")
    parser.add_argument("--limit",type=int,default=None,help="max FO images to analyze")
    args=parser.parse_args(argv)
    if args.install:
        print(json.dumps(install(),ensure_ascii=False,indent=2))
        return 0
    if args.verify:
        info=status()
        print(json.dumps(info,ensure_ascii=False,indent=2))
        return 0 if info["available"] else 2
    if args.prune_cache:
        from server.services.screen_search import prune_old_reference_cache
        print(json.dumps(prune_old_reference_cache(),ensure_ascii=False))
        return 0
    if not status()["available"]:
        print("XFeat не установлен. Запустите --install или перенесите веса и исходники.",file=sys.stderr)
        return 2
    # Import database and OpenCV only when actual analysis is requested.
    from server.services.screen_search import analyze_run
    def progress(item):
        print(json.dumps({"index":item["index"],"sam":item["assigned_sam"],
                          "status":item["status"],"reason":item["reason"],
                          "seconds":item["elapsed_seconds"]},ensure_ascii=False),flush=True)
    print(json.dumps(analyze_run(args.run_id,limit=args.limit,progress=progress),
                     ensure_ascii=False,indent=2))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
