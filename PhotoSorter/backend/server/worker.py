"""One exclusive DB-advisory-locked MegaLoc leader, FIFO jobs and crash recovery."""
from __future__ import annotations
import logging,os,signal,threading,time
import psycopg
from psycopg.rows import dict_row
from .database import connect,wait_and_initialize,DB_URL
from .services import heartbeat
from .db.repositories import work_queue
from .workers import reference_prepare,media_prepare
from .workers.warm_megaloc import WarmMegaLoc
from .jobs import ServerJob

logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s")
RUN=True
LEADER_KEY=723409139

def stop(*_):
    global RUN
    RUN=False

def claim_job():
    with connect() as db:
        return work_queue.claim_next(db)

def _configure_cpu(kind):
    # Apply the single persisted CPU setting only between FIFO tasks.
    from app.system.performance import set_runtime_threads
    from .services.compute_settings import for_worker
    from .services.worker_cpu_affinity import allocate
    with connect() as db:
        cpu_limit=for_worker(db,kind)
    # Restrict the actual worker process and inherited inference/ZIP threads.
    assigned=allocate(cpu_limit)
    set_runtime_threads(cpu_limit)
    return len(assigned) or cpu_limit

def _process_task(item,warm):
    if item['kind']=='reference_deletion':
        from .services import references
        try:
            references.process_deferred(item['id'])
        except Exception as exc:
            logging.exception('Reference deletion %s failed',item['id'])
            with connect() as db:
                db.execute("""UPDATE reference_deletion_tasks SET error=%s WHERE id=%s""",
                           (str(exc)[:1000],item['id']))
                db.execute("""UPDATE work_queue SET state='failed',finished_at=now()
                    WHERE reference_deletion_id=%s AND state='running'""",(item['id'],))
        return
    if item['kind']=='media_preparation':
        cpus=_configure_cpu(item['kind'])
        return media_prepare.run(item,stopping=lambda:not RUN,cpus=cpus)
    _configure_cpu(item['kind'])
    if item['kind']=='fo_processing':
        info=item['info']
        try:
            ServerJob(info,warm_megaloc=warm).run()
        except BaseException as exc:
            with connect() as db:
                work_queue.fail_fo(db,item['id'])
            raise
        return
    try:
        result=reference_prepare.run(item['id'],warm_megaloc=warm)
        logging.info('Reference preparation %s completed: %s',item['id'],result)
    except BaseException as exc:
        reason=f'{type(exc).__name__}: {exc}'[:1000]
        logging.exception('Reference preparation %s failed',item['id'])
        with connect() as db:
            status='interrupted' if isinstance(exc,reference_prepare.PreparationCancelled) else 'failed'
            work_queue.finish_preparation(db,item['id'],status,reason)
        if isinstance(exc,(KeyboardInterrupt,SystemExit)):
            raise

def _leader_watch(connection,stop_event):
    while not stop_event.wait(5):
        try:connection.execute("SELECT 1")
        except Exception:
            logging.critical("Lost the global MegaLoc leader DB connection; aborting to prevent parallel inference")
            os._exit(77)

def main():
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    wait_and_initialize()
    pulse,thread=heartbeat.start("megaloc")
    while RUN:
        try:
            with psycopg.connect(DB_URL,autocommit=True,row_factory=dict_row) as leader:
                acquired=leader.execute("SELECT pg_try_advisory_lock(%s)",(LEADER_KEY,)).fetchone()
                if not acquired or not next(iter(acquired.values())):
                    logging.info("Another MegaLoc worker owns global leader lock")
                    time.sleep(5)
                    continue
                with connect() as db:
                    work_queue.mark_interrupted(db)
                watch_stop=threading.Event()
                watcher=threading.Thread(target=_leader_watch,args=(leader,watch_stop),daemon=True)
                watcher.start()
                warm=WarmMegaLoc()
                next_warm_check=0.0
                try:
                    logging.info("MegaLoc leader ready; unified FIFO")
                    while RUN:
                        try:info=claim_job()
                        except Exception:
                            logging.exception('Could not claim next task; FIFO is blocked safely')
                            time.sleep(5)
                            continue
                        if info:
                            ident=info['id']
                            logging.info('Processing %s',ident)
                            try:_process_task(info,warm)
                            except Exception:logging.exception('Unhandled job exception for %s',ident)
                        else:
                            now=time.monotonic()
                            if now>=next_warm_check:
                                next_warm_check=now+30
                                from app.system.model_store import signature
                                try:
                                    fingerprint=signature()
                                    if fingerprint and not warm.ready_for(fingerprint):
                                        _configure_cpu('fo_processing')
                                        warm.get(fingerprint)
                                        logging.info('MegaLoc loaded and ready for FIFO jobs')
                                    elif not fingerprint:
                                        warm.close()
                                except Exception:logging.exception('Could not pre-load MegaLoc')
                            time.sleep(.5)
                finally:
                    warm.close()
                    watch_stop.set()
                    watcher.join(timeout=6)
                    leader.execute("SELECT pg_advisory_unlock(%s)",(LEADER_KEY,))
        except Exception:
            logging.exception("MegaLoc worker loop failed")
            time.sleep(3)

if __name__=="__main__":main()
