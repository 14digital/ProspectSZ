from datetime import datetime, timedelta, timezone
from app.core.database import SessionLocal
from app.models.entities import Company, Contact, Job, JobState, OutreachSequence, SequenceStep
from app.modules.jobs import enqueue, fail, lease
from app.modules.followups.service import stop_for_reply

def test_job_leasing_retry_and_expired_recovery():
    with SessionLocal() as db:
        job=enqueue(db,"TEST",{},"same"); assert enqueue(db,"TEST",{},"same").id==job.id; db.commit()
    with SessionLocal() as db:
        claimed=lease(db,"worker",1); assert claimed.state==JobState.LEASED; fail(db,claimed,"temporary")
        claimed.available_at=datetime.now(timezone.utc)-timedelta(seconds=1); claimed.state=JobState.LEASED; claimed.leased_until=datetime.now(timezone.utc)-timedelta(seconds=1); db.commit()
    with SessionLocal() as db: assert lease(db,"worker-2").id==job.id

def test_reply_stops_outstanding_followups():
    with SessionLocal() as db:
        company=Company(name="Care",normalized_name="care"); db.add(company); db.flush(); contact=Contact(company_id=company.id,name="Alex",role="Owner"); db.add(contact); db.flush(); seq=OutreachSequence(company_id=company.id,contact_id=contact.id,state="ACTIVE"); db.add(seq); db.flush(); step=SequenceStep(sequence_id=seq.id,day_offset=4,channel="EMAIL",state="SCHEDULED"); db.add(step); db.flush(); stop_for_reply(db,company.id,contact.id,"OPT_OUT"); db.commit(); assert seq.state=="STOPPED" and step.state=="CANCELLED"
