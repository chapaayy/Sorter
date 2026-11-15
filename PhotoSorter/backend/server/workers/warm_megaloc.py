"""One resident MegaLoc engine owned exclusively by the FIFO worker."""
from app.recognition.engines.megaloc.extractor import MegaLocEngine
from app.system.model_store import signature
from app.system.performance import cpu_performance


class WarmMegaLoc:
    def __init__(self):
        self.engine=None
        self.fingerprint=None

    def ready_for(self,fingerprint):
        return self.engine is not None and self.fingerprint==fingerprint

    def get(self,fingerprint=None):
        current=signature()
        if not current or (fingerprint is not None and current!=fingerprint):
            self.close()
            raise RuntimeError("MegaLoc не установлена или её версия изменилась")
        if not self.ready_for(current):
            self.close()
            engine=MegaLocEngine()
            if signature()!=current:
                engine.unload()
                raise RuntimeError("Версия MegaLoc изменилась во время загрузки")
            self.engine=engine
            self.fingerprint=current
        performance=cpu_performance()
        if self.engine.performance!=performance:
            self.engine.torch.set_num_threads(performance.threads)
            self.engine.performance=performance
        return self.engine

    def close(self):
        engine,self.engine=self.engine,None
        self.fingerprint=None
        if engine is not None:
            engine.unload()
