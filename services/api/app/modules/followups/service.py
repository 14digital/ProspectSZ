from sqlalchemy import select, update
from sqlalchemy.orm import Session
from app.models.entities import OutreachSequence, SequenceStep, Suppression

STOP_CATEGORIES={"OPT_OUT","NOT_INTERESTED","MEETING_REQUEST","POSITIVE_INTEREST"}
def stop_for_reply(db:Session,company_id:str,contact_id:str,category:str):
    if category not in STOP_CATEGORIES: return
    sequences=db.scalars(select(OutreachSequence).where(OutreachSequence.company_id==company_id,OutreachSequence.contact_id==contact_id,OutreachSequence.state.in_(["ACTIVE","PAUSED"]))).all()
    for seq in sequences:
        seq.state="STOPPED"; seq.stop_reason=category
        db.execute(update(SequenceStep).where(SequenceStep.sequence_id==seq.id,SequenceStep.state.in_(["NEEDS_APPROVAL","SCHEDULED"])).values(state="CANCELLED"))
