import os, socket, time
from app.core.database import SessionLocal
from app.models.entities import DiscoveryRun, Job, JobState, SourceImport
from app.modules.discovery.cqc import import_file
from app.modules.jobs import fail, lease

worker_id=f"{socket.gethostname()}:{os.getpid()}"
def work(job_id:str):
    with SessionLocal() as db:
        job=db.get(Job,job_id)
        if job.kind=="IMPORT_CQC":
            source=db.get(SourceImport,job.payload["source_import_id"]); run=db.get(DiscoveryRun,job.payload["discovery_run_id"]); result=import_file(db,source,run)
        else: raise ValueError(f"Unsupported job kind: {job.kind}")
        job=db.get(Job,job_id); job.state=JobState.SUCCEEDED; job.result=result; job.leased_until=None; job.worker_id=None; db.commit()
def main():
    while True:
        with SessionLocal() as db: job=lease(db,worker_id)
        if not job: time.sleep(2); continue
        try: work(job.id)
        except Exception as exc:
            with SessionLocal() as db: fail(db,db.get(Job,job.id),str(exc))
if __name__=="__main__": main()
