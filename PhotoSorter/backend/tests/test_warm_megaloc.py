from types import SimpleNamespace

from server.workers import warm_megaloc


def test_worker_reuses_one_model_and_applies_cpu_settings(monkeypatch):
    version,threads=["v1"],[6]
    loaded,unloaded,changes=[],[],[]
    def performance():
        return SimpleNamespace(threads=threads[0])
    def load():
        engine=SimpleNamespace(performance=performance(),
            torch=SimpleNamespace(set_num_threads=changes.append))
        engine.unload=lambda:unloaded.append(engine)
        loaded.append(engine)
        return engine
    monkeypatch.setattr(warm_megaloc,"signature",lambda:version[0])
    monkeypatch.setattr(warm_megaloc,"cpu_performance",performance)
    monkeypatch.setattr(warm_megaloc,"MegaLocEngine",load)
    warm=warm_megaloc.WarmMegaLoc()
    first=warm.get()
    assert warm.ready_for("v1")
    threads[0]=2
    assert warm.get("v1") is first
    assert changes==[2]
    assert len(loaded)==1
    version[0]="v2"
    second=warm.get("v2")
    assert second is not first
    assert unloaded==[first]
    warm.close()
    assert unloaded==[first,second]
