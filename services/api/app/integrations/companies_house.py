import httpx
from app.core.config import get_settings


class CompaniesHouseConnector:
    base="https://api.company-information.service.gov.uk"
    def search(self,name:str):
        key=get_settings().companies_house_api_key
        if not key: return {"status":"PENDING_CONFIGURATION","candidates":[]}
        with httpx.Client(timeout=15,auth=(key,"")) as client:
            response=client.get(f"{self.base}/search/companies",params={"q":name,"items_per_page":5}); response.raise_for_status()
        items=response.json().get("items",[])
        return {"status":"REVIEW_REQUIRED" if len(items)!=1 else "CANDIDATE_FOUND","candidates":[{"company_number":i.get("company_number"),"title":i.get("title"),"status":i.get("company_status"),"address":i.get("address_snippet")} for i in items]}
