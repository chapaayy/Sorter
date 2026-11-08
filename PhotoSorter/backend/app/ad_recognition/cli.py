"""Explicit stage-3 CLI. The current FIFO and ZIP workflow stay untouched."""
from __future__ import annotations
import argparse
import json
import sys
from . import dino,ocr

def main(argv=None):
    parser=argparse.ArgumentParser(description="DINOv2 layout matching + PP-OCRv5 check on CPU")
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--install-dino",action="store_true")
    group.add_argument("--install-ocr",action="store_true")
    group.add_argument("--verify",action="store_true")
    group.add_argument("--prune-cache",action="store_true",help="remove obsolete layout embeddings older than a week")
    group.add_argument("--run-id")
    parser.add_argument("--start-index",type=int,default=0)
    parser.add_argument("--limit",type=int,default=None)
    args=parser.parse_args(argv)
    if args.install_dino:
        print(json.dumps(dino.install(),ensure_ascii=False,indent=2));return 0
    if args.install_ocr:
        print(json.dumps(ocr.install(),ensure_ascii=False,indent=2));return 0
    if args.verify:
        info={"dino":dino.status(),"ocr":ocr.status()}
        print(json.dumps(info,ensure_ascii=False,indent=2))
        return 0 if info["dino"]["available"] else 2
    if args.prune_cache:
        from server.services.ad_recognition import prune_old_layout_cache
        print(json.dumps(prune_old_layout_cache(),ensure_ascii=False))
        return 0
    from server.services.ad_recognition import analyze_run
    def progress(item):
        print(json.dumps({"index":item["index"],"screen_id":item["screen_id"],
                          "status":item["status"],"reason":item["reason"],
                          "ocr":item.get("ocr",{}).get("status")},
                         ensure_ascii=False),flush=True)
    print(json.dumps(analyze_run(args.run_id,start_index=args.start_index,
                     limit=args.limit,progress=progress),ensure_ascii=False,indent=2))
    return 0

if __name__=="__main__":raise SystemExit(main())
