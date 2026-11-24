"""One immutable, streaming result manifest; no duplicate CSV or JSON array."""
import json
import os
from pathlib import Path

MANIFEST_NAME="manifest.rows.jsonl"

def export(model_dir,rows):
    path=Path(model_dir)/MANIFEST_NAME
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("x",encoding="utf-8") as stream:
        for index,row in enumerate(rows):
            stream.write(json.dumps({**row,"index":index},ensure_ascii=False,separators=(",",":"))+"\n")
        stream.flush()
        os.fsync(stream.fileno())
    return path
