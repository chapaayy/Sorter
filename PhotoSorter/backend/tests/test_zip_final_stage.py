"""The run must finish its result publication hook before completion; ZIP is on demand.

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
    class FinalizeJob(Job):
        def __init__(self):
            super().__init__({"id":"20261107T120000-abcdef123456",
                "status":"queued","models":{},"progress":{}})
            self.path=tmp_path
        def save(self):
            completed.append(self.info["status"])
        def log(self,*_args,**_kwargs):pass
        def finalize_results(self):
            completed.append("finalize")
            finalize(self)
    job=FinalizeJob()
    job.run()
    return job,completed


def test_result_publication_must_finish_before_run_becomes_completed(monkeypatch,tmp_path):
    def publication_success(job):
        from server.services.archive_pipeline import mark_on_demand
        mark_on_demand(job)
    job,trace=_execute(monkeypatch,tmp_path,publication_success)
    assert job.info["status"]=="completed"
    assert job.info["progress"]["overall_percent"]==100
    assert trace.index("finalize") < trace.index("completed")
    assert "megaloc" in trace
    assert job.info["archive_state"]=="on_demand"
    assert "archive_file" not in job.info


def test_result_publication_failure_never_marks_run_completed(monkeypatch,tmp_path):
    def publication_failure(job):
        raise OSError("disk full")
    job,trace=_execute(monkeypatch,tmp_path,publication_failure)
    assert job.info["models"]["megaloc"]["status"]=="completed"
    assert job.info["status"]=="failed"
    assert "completed" not in trace
    assert "disk full" in job.info["error"]
