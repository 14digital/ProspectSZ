from __future__ import annotations
from dataclasses import dataclass
from urllib.parse import urlparse
import httpx
from app.core.config import get_settings

class SearchUnavailable(Exception): pass

@dataclass(frozen=True)
class SearchResult:
    title:str; snippet:str; url:str

class SearchProvider:
    def search(self,query:str,limit:int=10)->list[SearchResult]:
        settings=get_settings()
        if settings.serper_api_key:
            response=httpx.post("https://google.serper.dev/search",headers={"X-API-KEY":settings.serper_api_key,"Content-Type":"application/json"},json={"q":query,"num":limit},timeout=25)
            if response.status_code>=400: raise SearchUnavailable(f"Search provider rejected the request ({response.status_code})")
            return [SearchResult(item.get("title",""),item.get("snippet",""),item.get("link","")) for item in response.json().get("organic",[])[:limit]]
        if settings.google_search_api_key and settings.google_search_engine_id:
            response=httpx.get("https://www.googleapis.com/customsearch/v1",params={"key":settings.google_search_api_key,"cx":settings.google_search_engine_id,"q":query,"num":min(limit,10)},timeout=25)
            if response.status_code>=400: raise SearchUnavailable(f"Google Custom Search rejected the request ({response.status_code})")
            return [SearchResult(item.get("title",""),item.get("snippet",""),item.get("link","")) for item in response.json().get("items",[])[:limit]]
        raise SearchUnavailable("Configure SERPER_API_KEY or working Google Custom Search credentials in .env")

def is_linkedin_profile(url:str)->bool:
    parsed=urlparse(url)
    return parsed.scheme=="https" and (parsed.hostname or "").lower() in {"linkedin.com","www.linkedin.com","uk.linkedin.com"} and parsed.path.startswith("/in/")
