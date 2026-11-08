"""Actual CPU inference with downloaded DINOv2 and PP-OCRv5 models in CI."""
from __future__ import annotations
import json
import resource
import time
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from . import dino,ocr,scoring

def main():
    import torch
    assert not torch.cuda.is_available() or dino.load().parameters().__next__().device.type=="cpu"
    rng=np.random.default_rng(3245)
    canvas=np.zeros((518,518,3),dtype="uint8")
    canvas[:]=rng.integers(30,210,(518,518,3),dtype="uint8")
    image=Image.fromarray(canvas)
    art=ImageDraw.Draw(image)
    art.rectangle((25,65,485,440),outline="white",width=9)
    art.text((120,180),"TEST 2026",fill="white")
    model=dino.load()
    started=time.perf_counter()
    vector=dino.embed(model,image)
    seconds=round(time.perf_counter()-started,3)
    assert vector.shape==(384,) and np.isclose(np.linalg.norm(vector),1,atol=1e-4)
    choice=scoring.rank(vector,[({"id":"example","name":"Demo","checksum":"a"*64,"version":1},vector)])
    assert choice["status"]=="matched" and choice["candidate_id"]=="example"
    info={"model":"DINOv2 ViT-S/14","device":"cpu","dimensions":len(vector),
          "self_cosine":choice["top"][0]["score"],"seconds":seconds,
          "peak_rss_kib":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    if ocr.status()["available"]:
        engine=ocr.load()
        started=time.perf_counter()
        russian=Image.new("RGB",(950,240),"white")
        font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",110)
        ImageDraw.Draw(russian).text((34,32),"СКИДКИ 50",font=font,fill="black")
        text=ocr.read(engine,russian)
        if not text:
            raise RuntimeError("PP-OCRv5 ru found no text in large Cyrillic control image")
        info["ocr"]={"version":ocr.VERSION,"device":"cpu",
                     "recognized_text":[row["text"] for row in text][:5],
                     "lines":len(text),
                     "seconds":round(time.perf_counter()-started,3)}
    else:
        raise RuntimeError("PP-OCRv5 weights missing in real recognition smoke test")
    print(json.dumps(info))
if __name__=="__main__":main()
