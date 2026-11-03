from __future__ import annotations
import ipaddress, re, socket, time
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
import requests
from bs4 import BeautifulSoup

AGENT="ProspectSZ/1.0 (+https://14digital.co.uk; public business research)"
ROLE=re.compile(r"\b(?:founder(?:\s*&\s*managing director)?|managing director|operations director|director of operations|registered manager|owner|chief executive|ceo)\b",re.I)
NAME=re.compile(r"[A-Z][A-Za-z'’\-]+(?:\s+[A-Z][A-Za-z'’\-]+){1,3}")
TEAM=re.compile(r"team|about|leadership|management|who-we-are|meet-us",re.I)
GENERIC_NAMES={"our team","meet the team","leadership team","management team","about us","who we are"}

class ResearchError(Exception): pass

@dataclass(frozen=True)
class Candidate:
    name:str; role:str; source_url:str; linkedin_url:str|None=None

def public_url(url:str)->str:
    try:
        parsed=urlparse(url)
        if parsed.scheme not in {"http","https"} or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None,80,443): raise ValueError
        addresses=socket.getaddrinfo(parsed.hostname,parsed.port or (443 if parsed.scheme=="https" else 80))
        if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses): raise ValueError
    except (ValueError,OSError): raise ResearchError("Website must resolve to a public HTTP(S) address") from None
    return url

class Reader:
    def __init__(self):
        self.session=requests.Session(); self.session.headers["User-Agent"]=AGENT; self.last_request=0.0; self.robots={}
    def get(self,url:str,origin:str)->requests.Response:
        for _ in range(5):
            public_url(url)
            if urlparse(url).hostname!=urlparse(origin).hostname: raise ResearchError("Cross-domain redirect skipped")
            time.sleep(max(0,0.8-(time.monotonic()-self.last_request))); self.last_request=time.monotonic()
            try:
                response=self.session.get(url,timeout=15,allow_redirects=False,stream=True)
                if response.is_redirect:
                    url=urljoin(url,response.headers.get("Location","")); continue
                response.raise_for_status(); body=bytearray()
                for chunk in response.iter_content(65536):
                    body.extend(chunk)
                    if len(body)>2_000_000: raise ResearchError("Page exceeds the 2 MB research limit")
                response._content=bytes(body); return response
            except requests.RequestException: raise ResearchError("Website request failed") from None
        raise ResearchError("Too many redirects")
    def page(self,url:str)->BeautifulSoup:
        parsed=urlparse(public_url(url)); origin=f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self.robots:
            parser=RobotFileParser()
            try:
                response=self.session.get(origin+"/robots.txt",timeout=10,headers={"User-Agent":AGENT},allow_redirects=False)
                if response.status_code==404: parser.parse(["User-agent: *","Allow: /"])
                else: response.raise_for_status(); parser.parse(response.text.splitlines())
            except requests.RequestException: raise ResearchError("Could not establish robots.txt permission; review manually") from None
            self.robots[origin]=parser
        parser=self.robots[origin]
        if not parser.can_fetch(AGENT,url): raise ResearchError("robots.txt disallows this page")
        delay=parser.crawl_delay(AGENT) or parser.crawl_delay("*") or 1
        if delay>30: raise ResearchError("Website requests a long crawl delay; review manually")
        time.sleep(max(0,delay-(time.monotonic()-self.last_request)))
        return BeautifulSoup(self.get(url,origin).content,"html.parser")

def candidates(soup:BeautifulSoup,source:str)->list[Candidate]:
    found=[]
    for element in soup.find_all(["article","li","div","section"]):
        text=element.get_text(" ",strip=True)
        role=ROLE.search(text)
        if not role or len(text)>700: continue
        linkedin=next((urljoin(source,a.get("href")) for a in element.find_all("a",href=True) if "linkedin.com/in/" in a.get("href","")),None)
        for heading in element.find_all(["h1","h2","h3","h4","strong"]):
            name=heading.get_text(" ",strip=True)
            if NAME.fullmatch(name) and name.lower() not in GENERIC_NAMES and not ROLE.search(name):
                item=Candidate(name,role.group(0).title(),source,linkedin)
                if item not in found: found.append(item)
    return found

def research_site(website:str)->tuple[list[Candidate],list[str]]:
    reader=Reader(); notes=[]; home=reader.page(website); pages=[(website,home)]
    origin=urlparse(website).hostname
    urls=[]
    for link in home.find_all("a",href=True):
        url=urljoin(website,link["href"]).split("#")[0]
        if urlparse(url).hostname==origin and TEAM.search(link.get_text(" ")+" "+url) and url not in urls and url!=website: urls.append(url)
    for url in urls[:4]:
        try: pages.append((url,reader.page(url)))
        except ResearchError as exc: notes.append(f"Skipped {url}: {exc}")
    found=[]
    for url,page in pages:
        for candidate in candidates(page,url):
            if not any(existing.name.lower()==candidate.name.lower() and existing.role.lower()==candidate.role.lower() for existing in found): found.append(candidate)
    return found,notes
