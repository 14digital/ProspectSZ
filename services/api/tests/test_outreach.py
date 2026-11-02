from app.core.database import SessionLocal
from app.models.entities import Company, ComplianceAssessment, Contact, DraftRevision, DraftState, SubscriberType, User

def seed():
    with SessionLocal() as db:
        company=Company(name="Example Care",normalized_name="example care",company_number="01234567",legal_status="active"); db.add(company); db.flush(); contact=Contact(company_id=company.id,name="Alex Smith",role="Operations Director",email="alex@example.com",verification_status="SOURCE_CONFIRMED",outreach_eligible=True); db.add(contact); db.commit(); return company.id,contact.id

def test_approval_invalidated_after_edit_and_unapproved_send_blocked(client,auth):
    company,contact=seed(); draft=client.post("/api/v1/outreach/drafts",headers=auth,json={"company_id":company,"contact_id":contact,"channel":"EMAIL","subject":"A useful question","content":"Would it be unreasonable to compare your recruitment workflow?"}).json()
    assert client.post(f"/api/v1/outreach/drafts/{draft['id']}/send",headers=auth).status_code==409
    approved=client.post(f"/api/v1/outreach/drafts/{draft['id']}/approve",headers=auth).json(); assert approved["state"]=="APPROVED"
    edited=client.patch(f"/api/v1/outreach/drafts/{draft['id']}",headers=auth,json={"subject":"Changed","content":"Changed content","version":approved["version"]}).json()
    assert edited["state"]=="EDITED" and client.post(f"/api/v1/outreach/drafts/{draft['id']}/send",headers=auth).status_code==409

def test_unknown_subscriber_and_suppression_block_send(client,auth):
    company,contact=seed(); draft=client.post("/api/v1/outreach/drafts",headers=auth,json={"company_id":company,"contact_id":contact,"channel":"EMAIL","content":"Hello"}).json(); client.post(f"/api/v1/outreach/drafts/{draft['id']}/approve",headers=auth)
    assert client.post(f"/api/v1/outreach/drafts/{draft['id']}/send",headers=auth).status_code==403
    assessment=client.post("/api/v1/compliance/assessments",headers=auth,json={"company_id":company,"contact_id":contact,"subscriber_type":"VERIFIED_CORPORATE","legal_entity_verified":True,"lawful_basis":"LEGITIMATE_INTERESTS","privacy_notice_reference":"https://14digital.co.uk/privacy"}); assert assessment.status_code==200
    client.post("/api/v1/suppression",headers=auth,json={"contact_id":contact,"reason":"OPT_OUT"})
    assert client.post(f"/api/v1/outreach/drafts/{draft['id']}/send",headers=auth).status_code==403

def test_mock_send_is_idempotent(client,auth):
    company,contact=seed(); client.post("/api/v1/compliance/assessments",headers=auth,json={"company_id":company,"contact_id":contact,"subscriber_type":"VERIFIED_CORPORATE","legal_entity_verified":True,"lawful_basis":"LEGITIMATE_INTERESTS","privacy_notice_reference":"https://14digital.co.uk/privacy"})
    draft=client.post("/api/v1/outreach/drafts",headers=auth,json={"company_id":company,"contact_id":contact,"channel":"EMAIL","content":"Hello"}).json(); client.post(f"/api/v1/outreach/drafts/{draft['id']}/approve",headers=auth)
    first=client.post(f"/api/v1/outreach/drafts/{draft['id']}/send",headers=auth); assert first.status_code==200
    second=client.post(f"/api/v1/outreach/drafts/{draft['id']}/send",headers=auth); assert second.status_code==409
