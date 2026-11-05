from app.models.entities import Company, CompanyResearch, Contact, EvidenceSource

DEFAULT_WEIGHTS = {"industry_fit":25,"size_complexity":20,"operational_opportunity":20,"channel_availability":15,"geography_fit":10,"timeliness":10}

PRIORITY_RULE_VERSION = "cqc-intent-1.0"


def seed_priority(company: Company) -> tuple[int, list[str]]:
    """Rank imported providers before costly contact enrichment.

    The score uses only facts already present in the official CQC import. It is
    a sales-research priority, not a claim that the company intends to buy.
    """
    if company.suppressed:
        return 0, ["Suppressed"]

    locations = list(company.locations)
    score = 20
    reasons = ["UK regulated adult-social-care provider +20"]

    ratings = {(location.cqc_rating or "").strip().lower() for location in locations}
    if "inadequate" in ratings:
        score += 30
        reasons.append("CQC Inadequate rating indicates urgent operational pressure +30")
    elif "requires improvement" in ratings:
        score += 24
        reasons.append("CQC Requires Improvement indicates operational pressure +24")

    count = len(locations)
    if count >= 5:
        score += 20
        reasons.append(f"{count} registered locations indicate workflow complexity +20")
    elif count >= 2:
        score += 12
        reasons.append(f"{count} registered locations indicate workflow complexity +12")
    elif count == 1:
        score += 4
        reasons.append("One registered location +4")

    service_text = " ".join(location.service_type or "" for location in locations).lower()
    if any(term in service_text for term in ("homecare", "domiciliary", "supported living")):
        score += 15
        reasons.append("Service mix fits recruitment, HR and care-workflow products +15")

    if company.website:
        score += 8
        reasons.append("Official website available for account research +8")
    if any(location.phone for location in locations):
        score += 7
        reasons.append("Public organisation phone available +7")

    return min(score, 100), reasons


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
