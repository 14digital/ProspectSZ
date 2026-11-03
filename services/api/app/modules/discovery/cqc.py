from __future__ import annotations
import csv, hashlib, re
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.entities import Company, CompanyIdentifier, CompanyLocation, DiscoveryRun, SourceImport, SourceRecord

LICENCE="CQC data reused under its published data terms; retain source URL, import date and identifiers."
ALIASES={
 "provider_id":["provider id","provider_id","providerid","cqc provider id (for office use only)"], "location_id":["location id","location_id","locationid","cqc location id (for office use only)"],
 "provider_name":["provider name","provider_name","providername","organisation name"], "location_name":["location name","location_name","locationname","name"],
 "service_type":["service type","service types","service_type","regulated activities","care home?"], "postcode":["postcode","postal code"], "phone":["phone","phone number","telephone"],
 "address":["address","location address"], "region":["region","local authority"], "rating":["overall rating","rating"], "website":["website","web address"]}

def norm(v:str)->str: return re.sub(r"[^a-z0-9]+"," ",v.lower()).strip()
def pick(row, key):
    normalized={norm(k):v for k,v in row.items() if k}
    return next((normalized.get(norm(a),"").strip() for a in ALIASES[key] if normalized.get(norm(a),"").strip()),"")

def file_sha(path:Path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()

def import_file(db:Session, source:SourceImport, run:DiscoveryRun):
    path=Path(source.file_path or "")
    created=locations=rejected=0
    try:
        with path.open("r",encoding="utf-8-sig",newline="") as handle:
            rows=csv.reader(handle)
            header=None
            for candidate in (next(rows,None) for _ in range(25)):
                if candidate is None: break
                names={norm(value) for value in candidate if value}
                has_name=any(norm(alias) in names for alias in ALIASES["provider_name"])
                has_id=any(norm(alias) in names for key in ("provider_id","location_id") for alias in ALIASES[key])
                if has_name and has_id:
                    header=candidate; break
            if not header: raise ValueError("CSV has no recognised CQC header row in its first 25 rows")
            reader=csv.DictReader(handle,fieldnames=header)
            headers={norm(value) for value in reader.fieldnames if value}
            has_provider_name=any(norm(alias) in headers for alias in ALIASES["provider_name"])
            has_identifier=any(norm(alias) in headers for key in ("provider_id","location_id") for alias in ALIASES[key])
            if not has_provider_name or not has_identifier:
                raise ValueError("CSV must include a provider name and a provider or location ID column")
            for index,row in enumerate(reader,2):
                provider_id,location_id=pick(row,"provider_id"),pick(row,"location_id")
                provider_name,location_name=pick(row,"provider_name"),pick(row,"location_name")
                external=location_id or provider_id or f"row-{index}"
                record=SourceRecord(source_import_id=source.id,external_key=external,payload={k:v for k,v in row.items() if k})
                if not provider_name or not (provider_id or location_id):
                    record.rejection_reason="MISSING_PROVIDER_ID_OR_NAME"; rejected+=1; db.add(record); continue
                company=db.scalar(select(Company).join(CompanyIdentifier).where(CompanyIdentifier.kind=="CQC_PROVIDER_ID",CompanyIdentifier.value==provider_id)) if provider_id else None
                if not company:
                    normalized=norm(provider_name); company=db.scalar(select(Company).where(Company.normalized_name==normalized,Company.country=="GB"))
                if not company:
                    company=Company(name=provider_name,normalized_name=norm(provider_name),website=pick(row,"website") or None)
                    db.add(company); db.flush(); created+=1
                if provider_id and not db.scalar(select(CompanyIdentifier).where(CompanyIdentifier.kind=="CQC_PROVIDER_ID",CompanyIdentifier.value==provider_id)):
                    db.add(CompanyIdentifier(company_id=company.id,kind="CQC_PROVIDER_ID",value=provider_id,source_url=source.source_url)); db.flush()
                if location_id and not db.scalar(select(CompanyLocation).where(CompanyLocation.cqc_location_id==location_id)):
                    db.add(CompanyLocation(company_id=company.id,cqc_location_id=location_id,cqc_provider_id=provider_id or None,name=location_name or provider_name,address=pick(row,"address") or None,postcode=pick(row,"postcode") or None,phone=pick(row,"phone") or None,region=pick(row,"region") or None,service_type=pick(row,"service_type") or None,cqc_rating=pick(row,"rating") or None,source_url=source.source_url)); locations+=1
                db.add(record)
        source.status="IMPORTED"; source.error=None; source.imported_at=datetime.now(timezone.utc); run.state="SUCCEEDED"; run.error=None; run.discovered_count=created
        db.commit(); return {"companies_created":created,"locations_created":locations,"records_rejected":rejected,"licence":LICENCE}
    except Exception as exc:
        db.rollback(); source=db.get(SourceImport,source.id); run=db.get(DiscoveryRun,run.id); source.status="FAILED"; source.error=str(exc)[:1000]; run.state="FAILED"; run.error=str(exc)[:1000]; db.commit(); raise
