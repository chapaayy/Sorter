"""Pre-write size limit for seekable Python producers (ZIP and metadata)."""
from fastapi import HTTPException

class BoundedWriter:
    def __init__(self,stream,limit):self.stream=stream;self.limit=limit
    def write(self,data):
        if self.stream.tell()+len(data)>self.limit:
            raise HTTPException(507,"Недостаточно зарезервированного места для создаваемого файла")
        return self.stream.write(data)
    def __getattr__(self,name):return getattr(self.stream,name)
