import io
from app.core.database import SessionLocal
from app.models.entities import Company, CompanyLocation, Job, JobState, SourceImport
from app.modules.discovery.cqc import import_file

CQC="""Provider ID,Location ID,Provider Name,Location Name,Service Type,Postcode,Overall Rating
P1,L1,Example Care Ltd,Example North,Domiciliary care,B1 1AA,Requires improvement
P1,L2,Example Care Ltd,Example South,Domiciliary care,B2 2BB,Good
P2,L3,Second Care,Second Home,Residential care,B3 3CC,Good
"""
CQC_SEARCH="""We found 7538 results for Homecare agencies. These results are listed below.

Name,Postcode,Phone number,Website,Service types,Provider name,CQC Provider ID (for office use only),CQC Location ID (for office use only)
Surrey Downs Homecare Ltd,RH4 1PT,07972108864,https://www.sdhomecare.co.uk,Homecare agencies,Surrey Downs Homecare Ltd,1-13081650040,1-13447576832
"""
def test_csv_import_groups_locations_and_deduplicates(client,auth,tmp_path):
    run=client.post("/api/v1/discovery-runs",headers=auth,json={"source":"CQC_CSV","target_count":20}).json()
    assert run["state"]=="AWAITING_UPLOAD"
    response=client.post(f"/api/v1/discovery-runs/{run['id']}/upload",headers=auth,files={"file":("cqc.csv",CQC,"text/csv")})
    assert response.status_code==202
    with SessionLocal() as db:
        job=db.get(Job,response.json()["job_id"]); source=db.get(SourceImport,response.json()["source_import_id"]); discovery=db.get(__import__("app.models.entities",fromlist=["DiscoveryRun"]).DiscoveryRun,run["id"])
        result=import_file(db,source,discovery); job.state=JobState.SUCCEEDED; db.commit()
        assert result["companies_created"]==2
        assert db.query(Company).count()==2 and db.query(CompanyLocation).count()==3
        example=db.query(Company).filter_by(normalized_name="example care ltd").one(); assert len(example.locations)==2
    duplicate=client.post(f"/api/v1/discovery-runs/{run['id']}/upload",headers=auth,files={"file":("same.csv",CQC,"text/csv")})
    assert duplicate.json()["duplicate"] is True

def test_malformed_csv_fails_without_silent_success(client,auth):
    run=client.post("/api/v1/discovery-runs",headers=auth,json={}).json(); response=client.post(f"/api/v1/discovery-runs/{run['id']}/upload",headers=auth,files={"file":("bad.csv","not useful\nvalue","text/csv")})
    with SessionLocal() as db:
        source=db.get(SourceImport,response.json()["source_import_id"]); discovery=db.get(__import__("app.models.entities",fromlist=["DiscoveryRun"]).DiscoveryRun,run["id"])
        import pytest
        with pytest.raises(ValueError,match="CQC header"):
            import_file(db,source,discovery)
        db.refresh(discovery)
        assert discovery.state=="FAILED" and discovery.error

def test_non_csv_and_large_upload_are_rejected(client,auth):
    run=client.post("/api/v1/discovery-runs",headers=auth,json={}).json()
    assert client.post(f"/api/v1/discovery-runs/{run['id']}/upload",headers=auth,files={"file":("x.exe",b"x")}).status_code==415

def test_official_cqc_search_export_with_preamble(client,auth):
    run=client.post("/api/v1/discovery-runs",headers=auth,json={}).json()
    response=client.post(f"/api/v1/discovery-runs/{run['id']}/upload",headers=auth,files={"file":("search.csv",CQC_SEARCH,"text/csv")})
    with SessionLocal() as db:
        source=db.get(SourceImport,response.json()["source_import_id"]); discovery=db.get(__import__("app.models.entities",fromlist=["DiscoveryRun"]).DiscoveryRun,run["id"])
        result=import_file(db,source,discovery)
        assert result["companies_created"]==1 and result["locations_created"]==1
        company=db.query(Company).filter_by(normalized_name="surrey downs homecare ltd").one()
        assert company.website=="https://www.sdhomecare.co.uk" and company.locations[0].service_type=="Homecare agencies"
        assert company.locations[0].phone=="07972108864"

def test_empty_discovery_run_can_be_deleted(client,auth):
    run=client.post("/api/v1/discovery-runs",headers=auth,json={}).json()
    assert client.delete(f"/api/v1/discovery-runs/{run['id']}",headers=auth).status_code==204
    assert client.get(f"/api/v1/discovery-runs/{run['id']}",headers=auth).status_code==404
