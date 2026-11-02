from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.entities import Company, Contact, ComplianceAssessment, SubscriberType, Suppression


def assess_eligibility(db: Session, company_id: str, contact_id: str):
    company=db.get(Company,company_id); contact=db.get(Contact,contact_id)
    if not company or not contact or contact.company_id != company_id: return False,"Company or contact not found"
    active=db.scalar(select(Suppression).where(Suppression.active.is_(True), ((Suppression.company_id==company_id)|(Suppression.contact_id==contact_id))))
    if company.suppressed or contact.suppressed or active: return False,"Suppression blocks outreach"
    assessment=db.scalar(select(ComplianceAssessment).where(ComplianceAssessment.company_id==company_id, ComplianceAssessment.contact_id==contact_id).order_by(ComplianceAssessment.created_at.desc()))
    if not assessment: return False,"No compliance assessment"
    if assessment.subscriber_type==SubscriberType.UNKNOWN: return False,"Unknown subscriber type blocks unsolicited email"
    if assessment.subscriber_type==SubscriberType.INDIVIDUAL and not assessment.lawful_basis: return False,"Individual subscriber requires documented lawful basis"
    if not assessment.legal_entity_verified: return False,"Legal entity is not verified"
    if not assessment.privacy_notice_reference: return False,"Privacy notice reference is missing"
    return bool(assessment.eligible), assessment.explanation
