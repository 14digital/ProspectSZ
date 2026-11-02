from app.models.entities import Company, CompanyResearch, Contact, EvidenceSource

DEFAULT_WEIGHTS = {"industry_fit":25,"size_complexity":20,"operational_opportunity":20,"channel_availability":15,"geography_fit":10,"timeliness":10}


def calculate(company: Company, research: CompanyResearch | None, contacts: list[Contact], evidence: list[EvidenceSource], weights=None):
    w = weights or DEFAULT_WEIGHTS; breakdown={}; missing=[]; proof=[]
    care_fit = company.industry == "adult_social_care" or bool(company.locations)
    breakdown["industry_fit"] = w["industry_fit"] if care_fit else 0
    if not care_fit: missing.append("care service classification")
    size_known = company.employee_count is not None
    complexity = (size_known and 50 <= company.employee_count <= 250) or len(company.locations) >= 2
    breakdown["size_complexity"] = w["size_complexity"] if complexity else (w["size_complexity"]//2 if len(company.locations)==1 else 0)
    if not size_known: missing.append("employee count")
    verified_ops = [e for e in evidence if e.category=="VERIFIED" and any(k in e.claim.lower() for k in ("recruit", "compliance", "onboard", "workflow", "requires improvement"))]
    inferred_ops = bool(research and research.inferred_opportunities)
    breakdown["operational_opportunity"] = w["operational_opportunity"] if verified_ops else (w["operational_opportunity"]//2 if inferred_ops else 0)
    if not verified_ops: missing.append("verified operational opportunity")
    available = [c for c in contacts if c.name and c.role and (c.email or c.linkedin_url)]
    breakdown["channel_availability"] = w["channel_availability"] if available else 0
    if not available: missing.append("verified decision-maker channel")
    breakdown["geography_fit"] = w["geography_fit"] if company.country=="GB" else 0
    timely = any(e.category=="VERIFIED" and any(k in e.claim.lower() for k in ("requires improvement","inadequate","registered","inspection")) for e in evidence)
    breakdown["timeliness"] = w["timeliness"] if timely else 0
    if not timely: missing.append("current business signal")
    total=sum(breakdown.values()); grade="A" if total>=80 else "B" if total>=60 else "C" if total>=40 else "D"
    proof.extend(e.claim for e in verified_ops[:3])
    explanation=f"{grade} lead ({total}/100). " + ("; ".join(proof) if proof else "Score uses available company-level evidence; missing items are not treated as negative facts.")
    return total, grade, breakdown, missing, explanation
