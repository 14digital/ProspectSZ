from app.core.database import SessionLocal
from app.models.entities import Company, CompanyLocation, CompanyResearch, Contact, EvidenceSource
from app.modules.qualification.service import calculate, seed_priority
from app.schemas.contracts import ScoreWeights
import pytest

def test_score_is_deterministic_and_evidence_backed():
    company=Company(name="Care",normalized_name="care",employee_count=100,country="GB"); company.locations=[CompanyLocation(name="One"),CompanyLocation(name="Two")]
    research=CompanyResearch(inferred_opportunities=["Recruitment workflow may be relevant"]); contact=Contact(name="Alex Smith",role="Operations Director",email="alex@example.com")
    evidence=[EvidenceSource(category="VERIFIED",claim="CQC rating requires improvement"),EvidenceSource(category="INFERRED",claim="May use paperwork")]
    first=calculate(company,research,[contact],evidence); second=calculate(company,research,[contact],evidence)
    assert first==second and first[0]==100 and first[1]=="A"
    assert "May use paperwork" not in first[4]

def test_missing_data_is_reported_not_assumed():
    company=Company(name="Unknown",normalized_name="unknown",country="GB")
    total,grade,_,missing,explanation=calculate(company,None,[],[])
    assert grade in {"C","D"} and "employee count" in missing and "missing" in explanation.lower()

def test_weights_must_total_100():
    with pytest.raises(ValueError): ScoreWeights(industry_fit=1)

def test_seed_priority_surfaces_regulatory_pressure_and_operational_complexity():
    company=Company(name="Priority Care",normalized_name="priority care",country="GB",website="https://example.com")
    company.locations=[
        CompanyLocation(name=f"Location {number}",cqc_rating="Requires improvement",service_type="Homecare agencies",phone="01234567890")
        for number in range(5)
    ]
    score,reasons=seed_priority(company)
    assert score==94
    assert any("operational pressure" in reason for reason in reasons)
    assert any("workflow complexity" in reason for reason in reasons)

def test_seed_priority_does_not_require_a_person_or_search_provider():
    company=Company(name="Single Care",normalized_name="single care",country="GB")
    company.locations=[CompanyLocation(name="Location",service_type="Residential care")]
    assert seed_priority(company)==(24,["UK regulated adult-social-care provider +20","One registered location +4"])
