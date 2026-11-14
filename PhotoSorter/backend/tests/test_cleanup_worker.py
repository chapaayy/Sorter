from threading import Event,Thread

from server.workers import cleanup as worker


def test_deletions_run_while_zip_maintenance_is_busy(monkeypatch):
    archive_started=Event()
    release_archive=Event()
    delete_seen=Event()
    stop=Event()

    def slow_zip(**_):
        archive_started.set()
        release_archive.wait(5)
        return []

    def delete():
        delete_seen.set()
        return []

    monkeypatch.setattr(worker,"STOPPED",stop)
    monkeypatch.setattr(worker,"wait_and_initialize",lambda:None)
    monkeypatch.setattr(worker.signal,"signal",lambda *_:None)
    monkeypatch.setattr(worker.heartbeat,"start",lambda _: (Event(),ThreadStub()))
    monkeypatch.setattr(worker.archive_retries,"process_pending",slow_zip)
    monkeypatch.setattr(worker.cleanup,"process_pending",delete)
    monkeypatch.setattr(worker.auto_processing,"schedule_ready",lambda:[])
    monkeypatch.setattr(worker.retention,"due_batch_ids",lambda:[])
    monkeypatch.setattr(worker.cleanup,"reconcile_incomplete_exports",lambda:[])
    monkeypatch.setattr(worker,"NEXT_GC",float("inf"))
    task=Thread(target=worker.main)
    task.start()
    try:
        assert archive_started.wait(2)
        assert delete_seen.wait(2)
        delete_seen.clear()
        assert delete_seen.wait(2),"a later deletion must not wait for the archive"
    finally:
        stop.set()
        release_archive.set()
        task.join(5)
    assert not task.is_alive()


class ThreadStub:
    def join(self):
        pass
