from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import current_user, require_admin, token_for, verify_password
from app.integrations.companies_house import CompaniesHouseConnector
from app.integrations.email import provider
from app.integrations.ai import generate_draft
from app.models.entities import *
from app.modules.compliance.service import assess_eligibility
from app.modules.followups.service import stop_for_reply
from app.modules.jobs import enqueue
from app.modules.outreach.service import add_revision, audit
from app.modules.qualification.service import calculate
from app.modules.research.site import ResearchError, research_site
from app.schemas.contracts import *

router=APIRouter()

@router.post("/auth/token",response_model=Token)
def login(form:OAuth2PasswordRequestForm=Depends(),db:Session=Depends(get_db)):
    user=db.scalar(select(User).where(User.email==form.username.lower()))
    if not user or not verify_password(form.password,user.password_hash): raise HTTPException(401,"Invalid credentials")
    return Token(access_token=token_for(user.id,user.role))

@router.post("/discovery-runs",response_model=DiscoveryOut,status_code=202)
def create_run(data:DiscoveryCreate,db:Session=Depends(get_db),user=Depends(current_user)):
    run=DiscoveryRun(campaign_id=data.campaign_id,source=data.source,target_count=data.target_count,state="AWAITING_UPLOAD"); db.add(run); db.flush(); audit(db,user.id,"discovery_run",run.id,"CREATED",data.model_dump()); db.commit(); return run
@router.get("/discovery-runs",response_model=list[DiscoveryOut])
def runs(db:Session=Depends(get_db),_=Depends(current_user)): return db.scalars(select(DiscoveryRun).order_by(DiscoveryRun.created_at.desc()).limit(100)).all()
@router.get("/discovery-runs/{run_id}",response_model=DiscoveryOut)
def run(run_id:str,db:Session=Depends(get_db),_=Depends(current_user)): return db.get(DiscoveryRun,run_id) or (_ for _ in ()).throw(HTTPException(404,"Run not found"))
@router.delete("/discovery-runs/{run_id}",status_code=204)
def delete_run(run_id:str,db:Session=Depends(get_db),user=Depends(current_user)):
    run=db.get(DiscoveryRun,run_id)
    if not run: raise HTTPException(404,"Run not found")
    if db.scalar(select(func.count()).select_from(SourceImport).where(SourceImport.discovery_run_id==run_id)):
        raise HTTPException(409,"A run with an uploaded source cannot be deleted")
    audit(db,user.id,"discovery_run",run.id,"DELETED"); db.delete(run); db.commit()
@router.post("/discovery-runs/{run_id}/cancel",response_model=DiscoveryOut)
def cancel_run(run_id:str,db:Session=Depends(get_db),user=Depends(current_user)):
    run=db.get(DiscoveryRun,run_id)
    if not run: raise HTTPException(404,"Run not found")
    if run.state in {"SUCCEEDED","FAILED"}: raise HTTPException(409,"Completed run cannot be cancelled")
    run.state="CANCELLED"; run.cancelled_at=datetime.now(timezone.utc); audit(db,user.id,"discovery_run",run.id,"CANCELLED"); db.commit(); return run
@router.post("/discovery-runs/{run_id}/upload",status_code=202)
async def upload_cqc(run_id:str,file:UploadFile=File(...),source_url:str|None=None,db:Session=Depends(get_db),user=Depends(current_user)):
    run=db.get(DiscoveryRun,run_id)
    if not run: raise HTTPException(404,"Run not found")
    if not (file.filename or "").lower().endswith(".csv"): raise HTTPException(415,"Only CSV files are accepted")
    content=await file.read(25_000_001)
    if len(content)>25_000_000: raise HTTPException(413,"CSV exceeds 25 MB")
    digest=hashlib.sha256(content).hexdigest(); existing=db.scalar(select(SourceImport).where(SourceImport.sha256==digest))
    if existing:
        if existing.status!="FAILED": return {"source_import_id":existing.id,"job_id":None,"duplicate":True}
        existing.discovery_run_id=run.id; existing.status="PENDING"; existing.error=None; existing.imported_at=None
        previous=db.scalar(select(Job).where(Job.idempotency_key==f"import-cqc:{digest}"))
        if previous:
            previous.state=JobState.QUEUED; previous.attempts=0; previous.available_at=datetime.now(timezone.utc); previous.leased_until=None; previous.worker_id=None; previous.last_error=None; previous.result=None; previous.payload={"source_import_id":existing.id,"discovery_run_id":run.id}
        else:
            previous=enqueue(db,"IMPORT_CQC",{"source_import_id":existing.id,"discovery_run_id":run.id},f"import-cqc:{digest}")
        run.state="QUEUED"; run.error=None; audit(db,user.id,"source_import",existing.id,"RETRIED",{"sha256":digest,"filename":file.filename}); db.commit()
        return {"source_import_id":existing.id,"job_id":previous.id,"duplicate":False,"retried":True}
    folder=get_settings().upload_dir; folder.mkdir(parents=True,exist_ok=True); path=folder/f"{digest}.csv"; path.write_bytes(content)
    source=SourceImport(discovery_run_id=run.id,source_type="CQC_CSV",source_url=source_url,version_label=file.filename,file_path=str(path),sha256=digest); db.add(source); db.flush()
    job=enqueue(db,"IMPORT_CQC",{"source_import_id":source.id,"discovery_run_id":run.id},f"import-cqc:{digest}"); run.state="QUEUED"; audit(db,user.id,"source_import",source.id,"UPLOADED",{"sha256":digest,"filename":file.filename}); db.commit()
    return {"source_import_id":source.id,"job_id":job.id,"duplicate":False}

@router.get("/companies",response_model=Page)
def companies(limit:int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0),stage:str|None=None,q:str|None=None,db:Session=Depends(get_db),_=Depends(current_user)):
    stmt=select(Company); count=select(func.count()).select_from(Company)
    if stage: stmt=stmt.where(Company.pipeline_stage==stage); count=count.where(Company.pipeline_stage==stage)
    if q: stmt=stmt.where(Company.name.ilike(f"%{q}%")); count=count.where(Company.name.ilike(f"%{q}%"))
    items=db.scalars(stmt.order_by(Company.created_at.desc()).limit(limit).offset(offset)).all()
    return Page(items=[CompanyOut.model_validate(i).model_dump() for i in items],total=db.scalar(count) or 0,limit=limit,offset=offset)
@router.get("/companies/{company_id}",response_model=CompanyOut)
def company(company_id:str,db:Session=Depends(get_db),_=Depends(current_user)):
    value=db.get(Company,company_id)
    if not value: raise HTTPException(404,"Company not found")
    return value
@router.get("/companies/{company_id}/dossier")
def company_dossier(company_id:str,db:Session=Depends(get_db),_=Depends(current_user)):
    company=db.get(Company,company_id)
    if not company: raise HTTPException(404,"Company not found")
    locations=db.scalars(select(CompanyLocation).where(CompanyLocation.company_id==company_id).order_by(CompanyLocation.name)).all()
    contacts=db.scalars(select(Contact).where(Contact.company_id==company_id).order_by(Contact.name)).all()
    contact_rows=[]
    for row in contacts:
        value=ContactOut.model_validate(row).model_dump(mode="json"); source=db.scalar(select(ContactSource).where(ContactSource.contact_id==row.id).order_by(ContactSource.collected_at.desc())); value["source_url"]=source.url if source else None; contact_rows.append(value)
    return {"company":CompanyOut.model_validate(company).model_dump(mode="json"),"locations":[{"id":row.id,"name":row.name,"postcode":row.postcode,"phone":row.phone,"region":row.region,"service_type":row.service_type,"cqc_rating":row.cqc_rating,"cqc_location_id":row.cqc_location_id,"source_url":row.source_url} for row in locations],"contacts":contact_rows}
@router.patch("/companies/{company_id}",response_model=CompanyOut)
def patch_company(company_id:str,data:CompanyPatch,db:Session=Depends(get_db),user=Depends(current_user)):
    company=db.get(Company,company_id)
    if not company: raise HTTPException(404,"Company not found")
    for key,value in data.model_dump(exclude_unset=True).items(): setattr(company,key,str(value) if key=="website" and value else value)
    company.version+=1; audit(db,user.id,"company",company.id,"UPDATED",data.model_dump(exclude_unset=True)); db.commit(); return company
@router.get("/companies/{company_id}/research")
def get_research(company_id:str,db:Session=Depends(get_db),_=Depends(current_user)):
    research=db.scalar(select(CompanyResearch).where(CompanyResearch.company_id==company_id).order_by(CompanyResearch.created_at.desc())); evidence=db.scalars(select(EvidenceSource).where(EvidenceSource.company_id==company_id)).all()
    return {"research":research,"evidence":evidence}
@router.post("/companies/{company_id}/research")
def save_research(company_id:str,data:ResearchInput,db:Session=Depends(get_db),user=Depends(current_user)):
    company=db.get(Company,company_id)
    if not company: raise HTTPException(404,"Company not found")
    research=CompanyResearch(company_id=company.id,**data.model_dump(exclude={"evidence"}),status="REVIEWED"); db.add(research)
    for e in data.evidence: db.add(EvidenceSource(company_id=company.id,category=e.category,claim=e.claim,url=str(e.url) if e.url else None,excerpt=e.excerpt))
    company.pipeline_stage=PipelineStage.RESEARCHED; db.flush(); audit(db,user.id,"company_research",research.id,"CREATED"); db.commit(); return {"id":research.id,"status":research.status}

@router.get("/contacts",response_model=list[ContactOut])
def contacts(company_id:str|None=None,db:Session=Depends(get_db),_=Depends(current_user)):
    stmt=select(Contact); stmt=stmt.where(Contact.company_id==company_id) if company_id else stmt; return db.scalars(stmt.limit(200)).all()
@router.post("/contacts",response_model=ContactOut)
def create_contact(data:ContactCreate,db:Session=Depends(get_db),user=Depends(current_user)):
    if not db.get(Company,data.company_id): raise HTTPException(404,"Company not found")
    contact=Contact(**data.model_dump(exclude={"source_url","channel","linkedin_url"}),linkedin_url=str(data.linkedin_url) if data.linkedin_url else None); db.add(contact); db.flush(); db.add(ContactSource(contact_id=contact.id,url=str(data.source_url),channel=data.channel)); audit(db,user.id,"contact",contact.id,"CREATED"); db.commit(); return contact
@router.patch("/contacts/{contact_id}",response_model=ContactOut)
def patch_contact(contact_id:str,data:ContactPatch,db:Session=Depends(get_db),user=Depends(current_user)):
    contact=db.get(Contact,contact_id)
    if not contact: raise HTTPException(404,"Contact not found")
    if contact.version!=data.version: raise HTTPException(409,"Contact was changed by another user")
    for k,v in data.model_dump(exclude={"version"},exclude_unset=True).items(): setattr(contact,k,str(v) if k=="linkedin_url" and v else v)
    contact.version+=1; audit(db,user.id,"contact",contact.id,"UPDATED"); db.commit(); return contact
@router.post("/companies/{company_id}/research-contacts")
def research_contacts(company_id:str,db:Session=Depends(get_db),user=Depends(current_user)):
    company=db.get(Company,company_id)
    if not company: raise HTTPException(404,"Company not found")
    if not company.website: raise HTTPException(409,"Confirm the official company website first")
    try: candidates,notes=research_site(company.website)
    except ResearchError as exc:
        audit(db,user.id,"company",company.id,"CONTACT_RESEARCH_BLOCKED",{"reason":str(exc)}); db.commit()
        return {"candidates":[],"notes":[],"manual_required":True,"message":f"Automatic scan unavailable: {exc}. Open the website or targeted Google search and save the evidence manually."}
    saved=[]
    for item in candidates:
        contact=db.scalar(select(Contact).where(Contact.company_id==company.id,func.lower(Contact.name)==item.name.lower(),func.lower(Contact.role)==item.role.lower()))
        if not contact:
            contact=Contact(company_id=company.id,name=item.name,role=item.role,linkedin_url=item.linkedin_url,verification_status="SOURCE_CONFIRMED",outreach_eligible=False); db.add(contact); db.flush(); db.add(ContactSource(contact_id=contact.id,url=item.source_url,channel="PUBLIC_WEBSITE"))
        elif item.linkedin_url and not contact.linkedin_url: contact.linkedin_url=item.linkedin_url
        saved.append({"id":contact.id,"name":contact.name,"role":contact.role,"source_url":item.source_url,"linkedin_url":contact.linkedin_url,"version":contact.version,"google_search_url":f"https://www.google.com/search?q={quote_plus(item.name+' '+company.name+' LinkedIn')}"})
    audit(db,user.id,"company",company.id,"CONTACT_RESEARCHED",{"candidate_count":len(saved),"pages_skipped":len(notes)}); db.commit()
    return {"candidates":saved,"notes":notes,"message":"No decision-maker candidate found; inspect the website manually" if not saved else None}
@router.get("/companies/{company_id}/companies-house")
def company_house(company_id:str,db:Session=Depends(get_db),_=Depends(current_user)):
    company=db.get(Company,company_id)
    if not company: raise HTTPException(404,"Company not found")
    return CompaniesHouseConnector().search(company.name)

@router.post("/companies/{company_id}/score",response_model=ScoreOut)
def score(company_id:str,weights:ScoreWeights=ScoreWeights(),db:Session=Depends(get_db),user=Depends(current_user)):
    company=db.get(Company,company_id)
    if not company: raise HTTPException(404,"Company not found")
    research=db.scalar(select(CompanyResearch).where(CompanyResearch.company_id==company_id).order_by(CompanyResearch.created_at.desc())); contacts=db.scalars(select(Contact).where(Contact.company_id==company_id)).all(); evidence=db.scalars(select(EvidenceSource).where(EvidenceSource.company_id==company_id)).all()
    total,grade,breakdown,missing,explanation=calculate(company,research,contacts,evidence,weights.model_dump()); result=LeadScore(company_id=company_id,total=total,grade=grade,breakdown=breakdown,missing=missing,explanation=explanation); db.add(result)
    if grade in {"A","B"}: company.pipeline_stage=PipelineStage.QUALIFIED
    db.flush(); audit(db,user.id,"lead_score",result.id,"CALCULATED",{"total":total,"grade":grade}); db.commit(); return result
@router.get("/companies/{company_id}/score",response_model=ScoreOut)
def latest_score(company_id:str,db:Session=Depends(get_db),_=Depends(current_user)):
    score=db.scalar(select(LeadScore).where(LeadScore.company_id==company_id).order_by(LeadScore.created_at.desc()))
    if not score: raise HTTPException(404,"Score not found")
    return score

@router.post("/compliance/assessments")
def compliance(data:ComplianceInput,db:Session=Depends(get_db),user=Depends(current_user)):
    eligible=data.subscriber_type=="VERIFIED_CORPORATE" and data.legal_entity_verified and bool(data.lawful_basis and data.privacy_notice_reference)
    explanation="Eligible subject to final suppression recheck" if eligible else "Incomplete or unknown compliance evidence blocks sending"
    assessment=ComplianceAssessment(**data.model_dump(),eligible=eligible,explanation=explanation); db.add(assessment); db.flush(); audit(db,user.id,"compliance_assessment",assessment.id,"CREATED",{"eligible":eligible}); db.commit(); return {"id":assessment.id,"eligible":eligible,"explanation":explanation}
@router.post("/suppression")
def suppress(data:SuppressionInput,db:Session=Depends(get_db),user=Depends(current_user)):
    if not (data.company_id or data.contact_id or data.email): raise HTTPException(422,"Company, contact or email is required")
    email_hash=hashlib.sha256(str(data.email).lower().encode()).hexdigest() if data.email else None
    row=Suppression(company_id=data.company_id,contact_id=data.contact_id,email_hash=email_hash,reason=data.reason,recorded_by=user.id); db.add(row)
    if data.company_id:
        company=db.get(Company,data.company_id)
        if company: company.suppressed=True
    if data.contact_id:
        contact=db.get(Contact,data.contact_id)
        if contact: contact.suppressed=True; stop_for_reply(db,contact.company_id,contact.id,"OPT_OUT")
    db.flush(); audit(db,user.id,"suppression",row.id,"CREATED",{"reason":data.reason}); db.commit(); return {"id":row.id,"active":True}
@router.get("/suppression")
def suppressions(db:Session=Depends(get_db),_=Depends(require_admin)): return db.scalars(select(Suppression).where(Suppression.active.is_(True))).all()

@router.get("/outreach/drafts",response_model=list[DraftOut])
def drafts(state:str|None=None,db:Session=Depends(get_db),_=Depends(current_user)):
    stmt=select(OutreachDraft); stmt=stmt.where(OutreachDraft.state==state) if state else stmt; return db.scalars(stmt.order_by(OutreachDraft.updated_at.desc()).limit(200)).all()
@router.post("/outreach/drafts",response_model=DraftOut)
def create_draft(data:DraftCreate,db:Session=Depends(get_db),user=Depends(current_user)):
    if not db.get(Company,data.company_id) or not db.get(Contact,data.contact_id): raise HTTPException(404,"Company or contact not found")
    draft=OutreachDraft(company_id=data.company_id,contact_id=data.contact_id,channel=data.channel,evidence_ids=data.evidence_ids); db.add(draft); db.flush(); add_revision(db,draft,data.subject,data.content,user.id); audit(db,user.id,"outreach_draft",draft.id,"CREATED"); db.commit(); return draft
@router.post("/outreach/drafts/generate",response_model=DraftOut)
def generate_outreach(data:DraftGenerate,db:Session=Depends(get_db),user=Depends(current_user)):
    company=db.get(Company,data.company_id); contact=db.get(Contact,data.contact_id)
    if not company or not contact or contact.company_id!=company.id: raise HTTPException(404,"Company or contact not found")
    evidence=db.scalars(select(EvidenceSource).where(EvidenceSource.id.in_(data.evidence_ids),EvidenceSource.company_id==company.id)).all() if data.evidence_ids else []
    try:
        generated=generate_draft(company={"name":company.name,"website":company.website,"legal_status":company.legal_status},contact={"name":contact.name,"role":contact.role},evidence=[{"category":e.category,"claim":e.claim,"url":e.url,"excerpt":e.excerpt} for e in evidence],objective=data.objective,channel=data.channel)
    except Exception as exc:
        raise HTTPException(503,f"Draft generation failed; no draft was saved: {str(exc)[:240]}") from None
    draft=OutreachDraft(company_id=company.id,contact_id=contact.id,channel=data.channel,evidence_ids=[e.id for e in evidence]); db.add(draft); db.flush(); add_revision(db,draft,generated.subject,generated.content,user.id); audit(db,user.id,"outreach_draft",draft.id,"AI_GENERATED",{"evidence_ids":draft.evidence_ids}); db.commit(); return draft
@router.patch("/outreach/drafts/{draft_id}",response_model=DraftOut)
def patch_draft(draft_id:str,data:DraftPatch,db:Session=Depends(get_db),user=Depends(current_user)):
    draft=db.get(OutreachDraft,draft_id)
    if not draft: raise HTTPException(404,"Draft not found")
    if draft.version!=data.version: raise HTTPException(409,"Draft was changed by another user")
    add_revision(db,draft,data.subject,data.content,user.id); audit(db,user.id,"outreach_draft",draft.id,"EDITED"); db.commit(); return draft
@router.post("/outreach/drafts/{draft_id}/approve",response_model=DraftOut)
def approve(draft_id:str,db:Session=Depends(get_db),user=Depends(current_user)):
    draft=db.get(OutreachDraft,draft_id)
    if not draft or not draft.current_revision_id: raise HTTPException(404,"Draft not found")
    db.add(Approval(draft_id=draft.id,revision_id=draft.current_revision_id,reviewer_id=user.id)); draft.state=DraftState.APPROVED; draft.version+=1; audit(db,user.id,"outreach_draft",draft.id,"APPROVED",{"revision_id":draft.current_revision_id}); db.commit(); return draft
@router.post("/outreach/drafts/{draft_id}/reject",response_model=DraftOut)
def reject(draft_id:str,db:Session=Depends(get_db),user=Depends(current_user)):
    draft=db.get(OutreachDraft,draft_id)
    if not draft: raise HTTPException(404,"Draft not found")
    draft.state=DraftState.REJECTED; draft.version+=1; audit(db,user.id,"outreach_draft",draft.id,"REJECTED"); db.commit(); return draft
@router.post("/outreach/drafts/{draft_id}/send")
def send(draft_id:str,db:Session=Depends(get_db),user=Depends(current_user)):
    draft=db.get(OutreachDraft,draft_id)
    if not draft or draft.state!=DraftState.APPROVED: raise HTTPException(409,"Only an approved unchanged revision can be sent")
    approval=db.scalar(select(Approval).where(Approval.draft_id==draft.id,Approval.revision_id==draft.current_revision_id,Approval.revoked_at.is_(None)))
    if not approval: raise HTTPException(409,"Approval does not match current revision")
    contact=db.get(Contact,draft.contact_id); eligible,reason=assess_eligibility(db,draft.company_id,draft.contact_id)
    if not eligible: raise HTTPException(403,reason)
    if draft.channel!="EMAIL": raise HTTPException(409,"LinkedIn messages must be sent manually")
    revision=db.get(DraftRevision,draft.current_revision_id); idem=f"send:{draft.id}:{revision.id}"; existing=db.scalar(select(EmailMessage).where(EmailMessage.idempotency_key==idem))
    if existing: return {"id":existing.id,"state":existing.state,"duplicate":True}
    settings=get_settings()
    if settings.email_provider!="mock" and not settings.live_email_enabled: raise HTTPException(403,"Live email is disabled")
    result=provider().send(to=contact.email,subject=revision.subject or "",content=revision.content,idempotency_key=idem)
    message=EmailMessage(draft_id=draft.id,revision_id=revision.id,idempotency_key=idem,provider=settings.email_provider,provider_message_id=result["provider_message_id"],state=result["state"],sent_at=datetime.now(timezone.utc)); db.add(message); draft.state=DraftState.SENT; db.flush(); audit(db,user.id,"email_message",message.id,"SENT",{"provider":settings.email_provider}); db.commit(); return {"id":message.id,"state":message.state,"duplicate":False}

@router.get("/followups")
def followups(db:Session=Depends(get_db),_=Depends(current_user)): return db.scalars(select(Task).where(Task.state=="OPEN").order_by(Task.due_at)).all()
@router.patch("/followups/{task_id}")
def patch_followup(task_id:str,data:FollowupPatch,db:Session=Depends(get_db),user=Depends(current_user)):
    task=db.get(Task,task_id)
    if not task: raise HTTPException(404,"Task not found")
    task.state=data.state; task.due_at=data.due_at or task.due_at; audit(db,user.id,"task",task.id,"UPDATED",data.model_dump(mode="json")); db.commit(); return task
@router.post("/replies")
def reply(company_id:str,contact_id:str,category:str,db:Session=Depends(get_db),user=Depends(current_user)):
    event=ReplyEvent(company_id=company_id,contact_id=contact_id,category=category,needs_review=category not in {"OPT_OUT"}); db.add(event); stop_for_reply(db,company_id,contact_id,category)
    if category=="OPT_OUT":
        db.add(Suppression(company_id=company_id,contact_id=contact_id,reason="OPT_OUT",recorded_by=user.id)); contact=db.get(Contact,contact_id); contact.suppressed=True
    db.flush(); audit(db,user.id,"reply_event",event.id,"RECORDED",{"category":category}); db.commit(); return {"id":event.id,"category":category}

@router.get("/pipeline")
def pipeline(db:Session=Depends(get_db),_=Depends(current_user)): return db.execute(select(Company.pipeline_stage,func.count()).group_by(Company.pipeline_stage)).all()
@router.patch("/pipeline/{company_id}")
def pipeline_patch(company_id:str,data:PipelinePatch,db:Session=Depends(get_db),user=Depends(current_user)):
    company=db.get(Company,company_id)
    if not company: raise HTTPException(404,"Company not found")
    if company.version!=data.version: raise HTTPException(409,"Company was changed by another user")
    company.pipeline_stage=data.stage; company.next_action=data.next_action; company.version+=1
    if data.opportunity_value is not None:
        opp=db.scalar(select(Opportunity).where(Opportunity.company_id==company.id)) or Opportunity(company_id=company.id); opp.value=data.opportunity_value; db.add(opp)
    audit(db,user.id,"company",company.id,"PIPELINE_CHANGED",{"stage":data.stage}); db.commit(); return CompanyOut.model_validate(company)
@router.get("/analytics/overview",response_model=AnalyticsOverview)
def overview(db:Session=Depends(get_db),_=Depends(current_user)):
    count=lambda model,*where: db.scalar(select(func.count()).select_from(model).where(*where)) or 0
    return AnalyticsOverview(companies_discovered=count(Company),companies_qualified=count(Company,Company.pipeline_stage==PipelineStage.QUALIFIED),drafts_requiring_approval=count(OutreachDraft,OutreachDraft.state.in_([DraftState.NEEDS_REVIEW,DraftState.EDITED])),emails_sent=count(EmailMessage,EmailMessage.state=="SENT"),positive_replies=count(ReplyEvent,ReplyEvent.category.in_(["POSITIVE_INTEREST","MEETING_REQUEST"])),meetings_booked=count(Company,Company.pipeline_stage==PipelineStage.MEETING_BOOKED),opportunities_created=count(Opportunity),overdue_followups=count(Task,Task.state=="OPEN",Task.due_at<datetime.now(timezone.utc)))
@router.get("/analytics/conversions")
def conversions(db:Session=Depends(get_db),_=Depends(current_user)): return {str(stage):count for stage,count in db.execute(select(Company.pipeline_stage,func.count()).group_by(Company.pipeline_stage)).all()}
@router.get("/integrations/status")
def integrations(_=Depends(current_user)): 
    s=get_settings(); return {"companies_house":{"configured":bool(s.companies_house_api_key)},"openai":{"configured":bool(s.openai_api_key)},"email":{"provider":s.email_provider,"live_enabled":s.live_email_enabled}}
@router.get("/jobs/{job_id}")
def job(job_id:str,db:Session=Depends(get_db),_=Depends(current_user)):
    value=db.get(Job,job_id)
    if not value: raise HTTPException(404,"Job not found")
    return value
