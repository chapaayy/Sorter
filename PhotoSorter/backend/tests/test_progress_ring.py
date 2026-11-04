"""Adaptive overall ring and ETA must use runtime measurements, not fixed %s."""
from app.jobs.overall_progress import OverallProgress
from app.jobs.runtime import Job
from app.jobs.progress import record


def test_no_percent_or_eta_before_neural_throughput_sample():
    tracker=OverallProgress()
    tracker.configure(120,189,['megaloc'],0)
    tracker.update(None,'validate_queries',0,189,0)
    tracker.update(None,'validate_queries',189,189,4)
    tracker.update(None,'validate_queries',0,189,4)
    tracker.update(None,'validate_queries',189,189,12)
    tracker.update('megaloc','loading',0,1,12)
    assert tracker.calculate(18)['overall_percent'] is None
    assert tracker.calculate(18)['estimated_remaining_seconds'] is None


def test_estimates_progress_for_entire_run_and_eta_adapts():
    tracker=OverallProgress()
    tracker.configure(120,189,['megaloc'],0)
    for model,stage,start,total,end in [
        (None,'validate_queries',0,189,8),
        (None,'validate_queries',8,189,16),
        ('megaloc','loading',16,1,20)]:
        tracker.update(model,stage,0,total,start)
        tracker.update(model,stage,total,total,end)
    tracker.update('megaloc','queries',0,189,20)
    tracker.update('megaloc','queries',30,189,50)
    info=tracker.calculate(50)
    assert 0 < info['overall_percent'] < 100
    assert info['estimated_remaining_seconds'] is not None
    assert info['estimated_remaining_seconds'] > 0
    tracker.update('megaloc','queries',80,189,80)
    second=tracker.calculate(80)
    assert second['overall_percent'] >= info['overall_percent']
    assert second['estimated_remaining_seconds'] >= 0
    assert tracker.calculate(100,finished=True)['overall_percent']==100


def test_stage_progress_includes_label_and_preserves_disk_write_throttle(monkeypatch):
    job=Job({'id':'20261104T000000-abcdef123456','status':'running','progress':{}})
    job.started_monotonic=0
    job.configure_progress(15,30,['megaloc'])
    saves=[]
    monkeypatch.setattr(job,'save',lambda:saves.append(job.info['progress'].copy()))
    times=iter([5,6,7,8,9])
    monkeypatch.setattr('app.jobs.progress.time.monotonic', lambda:next(times))
    record(job,None,'validate_queries',0,30,'')
    record(job,None,'validate_queries',30,30,'')
    record(job,'megaloc','loading',0,1,'')
    record(job,'megaloc','loading',1,1,'')
    record(job,'megaloc','queries',0,30,'')
    assert saves[-1]['stage_label']=='MegaLoc — вычисление признаков ФО'
    assert saves[-1]['overall_percent'] is None


def test_grouping_never_uses_phash_or_color_and_records_diagnostics(tmp_path):
    import numpy as np
    from pathlib import Path
    from app.recognition.grouping.finder import find_groups
    paths=[tmp_path/f'{i}.JPG' for i in range(3)]  # deliberately nonexistent images
    groups=find_groups(paths,[np.array([1,0]),np.array([1,0]),np.array([0,1])])
    assert [len(g.members) for g in groups]==[2,1]
    assert groups[0].min_similarity == 1.0
    assert groups[0].nearest_other_group=='G0002'
    assert 'сходство' in groups[0].separation_reason.lower()


def test_groups_are_built_before_any_reference_inference(tmp_path):
    from collections import Counter
    import numpy as np
    from pathlib import Path
    from app.recognition.pipeline import match_grouped_megaloc
    fo=[tmp_path/'fo_a.jpg',tmp_path/'fo_b.jpg']
    sample=tmp_path/'sample.jpg'
    visited=[]
    class Engine:
        def extract(self,path):
            visited.append(Path(path).name)
            return np.array([1.,0.],dtype=np.float32)
    def check_group(paths,vectors,**kwargs):
        assert len(vectors)==2
        assert 'sample.jpg' not in visited
        from app.recognition.grouping.finder import find_groups
        return find_groups(paths,vectors,**kwargs)
    rows=match_grouped_megaloc(Engine(),[(sample,'SAM-0001')],fo,grouping_fn=check_group)
    assert visited==['fo_a.jpg','fo_b.jpg','sample.jpg']
    assert rows[0]['group_id']==rows[1]['group_id']
