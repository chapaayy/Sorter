"""Estimate remaining serial media work from FFmpeg's timeline and measured speed."""
from dataclasses import dataclass
from math import isfinite

MIB = 1024**2


@dataclass(frozen=True)
class Work:
    kind: str
    units: float
    # Heuristic used for relative progress and when a different kind has
    # already provided a timing sample. Never presented as measured time.
    baseline: float


def work(size, target, metadata=None, *, video=False):
    if not video:
        units = max(1, size/MIB)
        return Work('photo:'+target, units, .16*units+.15)
    if metadata is None:
        units = max(1,size/MIB)
        return Work('unknown:'+target,units,.9*units+1)
    from .formats import compatible_streams
    copy_video,copy_audio=compatible_streams(metadata,target)
    if copy_video and copy_audio:
        units=max(1,size/MIB)
        return Work('remux:'+target,units,.02*units+.3)
    length = metadata.duration
    if not length:
        units=max(1,size/MIB)
        return Work('unknown:'+target,units,.9*units+1)
    if copy_video:
        return Work('audio:'+target,length,max(.5,length*.12))
    # Normalize by pixels and frame rate so a 4K/60 clip does not weigh
    # the same as a 720p/25 clip of the same duration.
    units=length*max(.08,metadata.pixels/2073600)*max(.25,metadata.fps/30)
    return Work('encode:'+target,units,max(.5,units*(1.1 if target=='mp4' else 2)))


class Estimate:
    def __init__(self, plan):
        self.plan=plan
        self.rates={}
        self.weights=[0.]
        self.pending={}
        self.index=0
        for item in plan:
            self.weights.append(self.weights[-1]+item.baseline)
            base,units=self.pending.get(item.kind,(0,0))
            self.pending[item.kind]=(base+item.baseline,units+item.units)

    def advance(self,index):
        while self.index<index:
            item=self.plan[self.index]
            base,units=self.pending[item.kind]
            self.pending[item.kind]=(base-item.baseline,units-item.units)
            self.index+=1

    def observe(self,index,fraction,seconds):
        if not (fraction>0 and seconds>0 and isfinite(seconds)):
            return
        item=self.plan[index]
        rate=seconds/(item.units*fraction)
        if not isfinite(rate):return
        previous=self.rates.get(item.kind)
        self.rates[item.kind]=rate if previous is None else .7*previous+.3*rate

    def snapshot(self,index,fraction):
        if not self.plan:return None,None
        self.advance(index)
        fraction=min(.99,max(0,fraction))
        total=self.weights[-1]
        done=self.weights[index]
        if index<len(self.plan):done+=self.plan[index].baseline*fraction
        percent=min(99.9,100*done/total)
        if index>=len(self.plan) or self.plan[index].kind not in self.rates:return percent,None
        item=self.plan[index]
        elapsed=sum(base if kind not in self.rates else units*self.rates[kind]
                    for kind,(base,units) in self.pending.items())
        elapsed-=fraction*item.units*self.rates[item.kind]
        return percent,max(1,elapsed)
