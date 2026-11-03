from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, model_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel): access_token: str; token_type: str = "bearer"
class DiscoveryCreate(BaseModel): campaign_id: str | None = None; source: Literal["CQC_CSV", "MANUAL_CSV"] = "CQC_CSV"; target_count: int = Field(20, ge=1, le=100)
class DiscoveryOut(ORMModel): id: str; state: str; source: str; target_count: int; discovered_count: int; qualified_count: int; error: str | None; created_at: datetime
class CompanyPatch(BaseModel): name: str | None=None; trading_name: str|None=None; website: HttpUrl|None=None; company_number: str|None=None; legal_status: str|None=None; employee_count: int|None=Field(None,ge=1); pipeline_stage: str|None=None; next_action: str|None=None
class CompanyOut(ORMModel): id: str; name: str; trading_name: str|None; website: str|None; company_number: str|None; legal_status: str|None; employee_count: int|None; pipeline_stage: str; suppressed: bool; version: int; created_at: datetime
class ContactCreate(BaseModel): company_id: str; name: str=Field(min_length=2,max_length=200); role: str=Field(min_length=2,max_length=160); email: EmailStr|None=None; phone: str|None=None; linkedin_url: HttpUrl|None=None; source_url: HttpUrl; channel: str="PUBLIC_WEBSITE"
class ContactPatch(BaseModel): name: str|None=None; role: str|None=None; email: EmailStr|None=None; phone: str|None=None; linkedin_url: HttpUrl|None=None; verification_status: str|None=None; outreach_eligible: bool|None=None; version: int
class ContactOut(ORMModel): id: str; company_id: str; name: str; role: str; email: str|None; phone: str|None; linkedin_url: str|None; verification_status: str; outreach_eligible: bool; suppressed: bool; version: int
class EvidenceInput(BaseModel): category: Literal["VERIFIED","INFERRED","UNKNOWN"]; claim: str=Field(max_length=1000); url: HttpUrl|None=None; excerpt: str|None=Field(None,max_length=500)
class ResearchInput(BaseModel): confirmed_facts: list[str]=[]; inferred_opportunities: list[str]=[]; missing_information: list[str]=[]; relevant_services: list[str]=[]; suggested_roles: list[str]=[]; evidence: list[EvidenceInput]=[]
class ScoreWeights(BaseModel):
    industry_fit: int=25
    size_complexity: int=20
    operational_opportunity: int=20
    channel_availability: int=15
    geography_fit: int=10
    timeliness: int=10

    @model_validator(mode="after")
    def totals_100(self):
        if sum(self.model_dump().values()) != 100: raise ValueError("Scoring weights must total 100")
        return self
class ScoreOut(ORMModel): id: str; company_id: str; total: int; grade: str; breakdown: dict[str,Any]; missing: list[str]; rule_version: str; explanation: str
class ComplianceInput(BaseModel): company_id: str; contact_id: str|None=None; subscriber_type: Literal["VERIFIED_CORPORATE","VERIFIED_INDIVIDUAL","UNKNOWN"]; legal_entity_verified: bool=False; lawful_basis: str|None=None; lia_reference: str|None=None; privacy_notice_reference: str|None=None
class SuppressionInput(BaseModel): company_id: str|None=None; contact_id: str|None=None; email: EmailStr|None=None; reason: str=Field(min_length=2,max_length=120)
class DraftCreate(BaseModel): company_id: str; contact_id: str; channel: Literal["EMAIL","LINKEDIN"]; subject: str|None=Field(None,max_length=300); content: str=Field(min_length=1,max_length=5000); evidence_ids: list[str]=[]
class DraftGenerate(BaseModel): company_id: str; contact_id: str; channel: Literal["EMAIL","LINKEDIN"] = "EMAIL"; evidence_ids: list[str]=[]; objective: str=Field("Start a relevant, low-pressure conversation",max_length=500)
class DraftPatch(BaseModel): subject: str|None=Field(None,max_length=300); content: str=Field(min_length=1,max_length=5000); version: int
class DraftOut(ORMModel): id: str; company_id: str; contact_id: str; channel: str; state: str; current_revision_id: str|None; version: int; created_at: datetime
class PipelinePatch(BaseModel): stage: str; next_action: str|None=None; opportunity_value: float|None=Field(None,ge=0); version: int
class FollowupPatch(BaseModel): state: Literal["OPEN","DONE","PAUSED","CANCELLED"]; due_at: datetime|None=None
class Page(BaseModel): items: list[Any]; total: int; limit: int; offset: int
class AnalyticsOverview(BaseModel): companies_discovered:int; companies_qualified:int; drafts_requiring_approval:int; emails_sent:int; positive_replies:int; meetings_booked:int; opportunities_created:int; overdue_followups:int
class ErrorResponse(BaseModel): code: str; message: str; details: dict[str,Any]|None=None
