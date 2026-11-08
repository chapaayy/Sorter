"""The run cannot become completed until its full ZIP is prepared.

CPU inference, DB and user photo directories are not touched by these unit tests.
"""
from __future__ import annotations

from app.jobs.runtime import Job


def _execute(monkeypatch,tmp_path,finalize):
    import app.jobs.worker as worker
    completed=[]
    def inference(job):
        completed.append("megaloc")
        job.info["models"]["megaloc"]={"status":"completed"}
    monkeypatch.setattr(worker,"process",inference)
    class ZIPJob(Job):
        def __init__(self):
            super().__init__({"id":"20261107T120000-abcdef123456",
                "status":"queued","models":{},"progress":{}})
            self.path=tmp_path
        def save(self):
            completed.append(self.info["status"])
        def log(self,*_args,**_kwargs):pass
        def finalize_results(self):
            completed.append("zip")
            finalize(self)
    job=ZIPJob()
    job.run()
    return job,completed


def test_full_zip_must_finish_before_run_becomes_completed(monkeypatch,tmp_path):
    def zip_success(job):
        job.info["archive_state"]="ready"
    job,trace=_execute(monkeypatch,tmp_path,zip_success)
    assert job.info["status"]=="completed"
    assert job.info["progress"]["overall_percent"]==100
    assert trace.index("zip") < trace.index("completed")
    assert "megaloc" in trace


def test_zip_failure_never_marks_run_completed(monkeypatch,tmp_path):
    def zip_failure(job):
        job.info["archive_state"]="failed"
        raise OSError("disk full")
    job,trace=_execute(monkeypatch,tmp_path,zip_failure)
    assert job.info["models"]["megaloc"]["status"]=="completed"
    assert job.info["archive_state"]=="failed"
    assert job.info["status"]=="failed"
    assert "completed" not in trace
    assert "disk full" in job.info["error"]

def test_integrated_zip_completed_with_individual_photo_errors_is_explicit(monkeypatch,tmp_path):
    import app.jobs.worker as worker
    monkeypatch.setattr(worker,"process",lambda job:job.info["models"].update(
        {"megaloc":{"status":"completed"}}))
    class Integrated(Job):
        def __init__(self):
            super().__init__({"id":"20261108T120000-abcdef123456","status":"queued",
                "models":{},"progress":{},"ad_pipeline":{"enabled":True,"errors":2}})
            self.path=tmp_path
        def save(self):pass
        def log(self,*args):pass
        def finalize_results(self):
            self.info["archive_state"]="ready"
    job=Integrated()
    job.run()
    assert job.info["status"]=="completed_with_errors"
    assert job.info["archive_state"]=="ready"
    assert job.info["progress"]["overall_percent"]==100
