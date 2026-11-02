import hashlib
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.entities import Approval, DraftRevision, DraftState, OutreachDraft, AuditEvent


def add_revision(db:Session,draft:OutreachDraft,subject:str|None,content:str,user_id:str):
    latest=db.scalar(select(DraftRevision).where(DraftRevision.draft_id==draft.id).order_by(DraftRevision.number.desc()))
    number=(latest.number if latest else 0)+1
    revision=DraftRevision(draft_id=draft.id,number=number,subject=subject,content=content,content_hash=hashlib.sha256((subject or ""+"\n"+content).encode()).hexdigest(),created_by=user_id)
    db.add(revision); db.flush(); draft.current_revision_id=revision.id
    if draft.state==DraftState.APPROVED:
        approval=db.scalar(select(Approval).where(Approval.draft_id==draft.id,Approval.revoked_at.is_(None)).order_by(Approval.approved_at.desc()))
        if approval: approval.revoked_at=datetime.now(timezone.utc)
    draft.state=DraftState.EDITED if latest else DraftState.NEEDS_REVIEW; draft.version+=1
    return revision


def audit(db,actor,entity,entity_id,action,detail=None):
    db.add(AuditEvent(actor_id=actor,entity_type=entity,entity_id=entity_id,action=action,detail=detail or {}))
