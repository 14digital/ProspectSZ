from datetime import datetime, timedelta, timezone
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from app.models.entities import Job, JobState

def enqueue(db:Session,kind:str,payload:dict,idempotency_key:str):
    existing=db.scalar(select(Job).where(Job.idempotency_key==idempotency_key))
    if existing: return existing
    job=Job(kind=kind,payload=payload,idempotency_key=idempotency_key); db.add(job); db.flush(); return job

def lease(db:Session,worker_id:str,seconds=60):
    now=datetime.now(timezone.utc)
    query=(select(Job).where(Job.attempts<Job.max_attempts,Job.available_at<=now,
        or_(Job.state==JobState.QUEUED,(Job.state==JobState.LEASED)&(Job.leased_until<now)))
        .order_by(Job.available_at).with_for_update(skip_locked=True).limit(1))
    job=db.scalar(query)
    if not job: return None
    job.state=JobState.LEASED; job.leased_until=now+timedelta(seconds=seconds); job.worker_id=worker_id; job.attempts+=1; db.commit(); return job

def fail(db:Session,job:Job,error:str):
    job.last_error=error[:2000]; job.leased_until=None; job.worker_id=None
    if job.attempts>=job.max_attempts: job.state=JobState.FAILED
    else: job.state=JobState.QUEUED; job.available_at=datetime.now(timezone.utc)+timedelta(seconds=min(300,2**job.attempts))
    db.commit()
