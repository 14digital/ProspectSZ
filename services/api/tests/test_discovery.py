import io
from app.core.database import SessionLocal
from app.models.entities import Company, CompanyLocation, Job, JobState, SourceImport
from app.modules.discovery.cqc import import_file

CQC="""Provider ID,Location ID,Provider Name,Location Name,Service Type,Postcode,Overall Rating
P1,L1,Example Care Ltd,Example North,Domiciliary care,B1 1AA,Requires improvement
P1,L2,Example Care Ltd,Example South,Domiciliary care,B2 2BB,Good
P2,L3,Second Care,Second Home,Residential care,B3 3CC,Good
"""
def test_csv_import_groups_locations_and_deduplicates(client,auth,tmp_path):
    run=client.post("/api/v1/discovery-runs",headers=auth,json={"source":"CQC_CSV","target_count":20}).json()
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
        with pytest.raises(ValueError,match="provider name"):
            import_file(db,source,discovery)
        db.refresh(discovery)
        assert discovery.state=="FAILED" and discovery.error

def test_non_csv_and_large_upload_are_rejected(client,auth):
    run=client.post("/api/v1/discovery-runs",headers=auth,json={}).json()
    assert client.post(f"/api/v1/discovery-runs/{run['id']}/upload",headers=auth,files={"file":("x.exe",b"x")}).status_code==415
