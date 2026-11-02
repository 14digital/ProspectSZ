"""Source-backed prospecting. No SMTP, messaging, or automatic execution."""
from __future__ import annotations

import csv
import io
import ipaddress
import json
import os
import re
import socket
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

AGENT = "ProspectSZ/1.0 (+https://14digital.co.uk; public business research)"
CARE = re.compile(r"\b(care|supported living|homecare|domiciliary|nursing)\b", re.I)
ROLE = re.compile(r"\b(?:operations director|director of operations|registered manager|managing director|owner|founder)\b", re.I)


class PipelineError(Exception):
    """An actionable, safe-to-display pipeline error."""


@dataclass
class Prospect:
    company_name: str
    website: str
    discovery_source: str = "Manual import"
    employee_count: int | None = None
    employee_source: str = ""
    regulator_url: str = ""
    target_name: str = ""
    target_role: str = ""
    contact_source: str = ""
    verified_email: str = ""
    verification_status: str = "not_checked"
    verified_at: str = ""
    drafted_message: str = ""
    review_status: str = "research"
    notes: list[str] = field(default_factory=list)
    cqc_rating: str = "Unknown"
    review_signal: str = "Unknown"
    cqc_source: str = ""
    phone: str = ""
    phone_source: str = ""
    linkedin_url: str = ""
    do_not_contact: bool = False

    def export(self):
        return asdict(self)


def public_url(url: str) -> str:
    """Reject local/private destinations, including redirect targets."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in {"https", "http"} or not parsed.hostname:
            raise ValueError
        if parsed.username or parsed.password or parsed.port not in (None, 80, 443):
            raise ValueError
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise ValueError
    except (ValueError, OSError):
        raise PipelineError("Website must resolve to a public HTTP(S) address.") from None
    return url


class WebReader:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = AGENT
        self.robots = {}
        self.last_request = 0.0

    def get(self, url: str, origin: str | None = None) -> str:
        for _ in range(5):
            public_url(url)
            if origin and urlparse(url).hostname != urlparse(origin).hostname:
                raise PipelineError("Cross-domain crawl redirect skipped.")
            time.sleep(max(0, 1.0 - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            try:
                with self.session.get(url, timeout=20, allow_redirects=False, stream=True) as r:
                    if r.is_redirect:
                        url = urljoin(url, r.headers.get("Location", ""))
                        continue
                    r.raise_for_status()
                    body = bytearray()
                    for chunk in r.iter_content(65536):
                        body.extend(chunk)
                        if len(body) > 2_000_000:
                            raise PipelineError("Page exceeds the 2 MB research limit.")
                    return body.decode(r.encoding or "utf-8", errors="replace")
            except requests.RequestException:
                raise PipelineError("Website request failed; check availability and network policy.") from None
        raise PipelineError("Too many redirects.")

    def page(self, url: str) -> BeautifulSoup:
        parsed = urlparse(public_url(url))
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self.robots:
            parser = RobotFileParser()
            try:
                parser.parse(self.get(origin + "/robots.txt", origin).splitlines())
            except PipelineError:
                raise PipelineError("Cannot establish robots.txt permission; review this website manually.") from None
            self.robots[origin] = parser
        parser = self.robots[origin]
        if not parser.can_fetch(AGENT, url):
            raise PipelineError("robots.txt disallows this page.")
        delay = parser.crawl_delay(AGENT) or parser.crawl_delay("*") or 1
        if delay > 30:
            raise PipelineError("Site requests a long crawl delay; review manually.")
        time.sleep(max(0, delay - (time.monotonic() - self.last_request)))
        return BeautifulSoup(self.get(url, origin), "html.parser")


def api_get(url: str, *, params=None, headers=None):
    try:
        response = requests.get(url, params=params, headers=headers, timeout=25)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError):
        # Never expose provider request URLs: they can contain API keys.
        raise PipelineError("Provider request failed. Check the API key, quota, and allowed hostname.") from None


def discover(query: str, key: str, limit: int = 10) -> list[Prospect]:
    if not key:
        raise PipelineError("Configure BRAVE_SEARCH_API_KEY or import a company CSV.")
    result = api_get("https://api.search.brave.com/res/v1/web/search",
                     params={"q": query, "country": "GB", "count": min(limit, 20)},
                     headers={"X-Subscription-Token": key, "Accept": "application/json"})
    prospects, seen = [], set()
    for item in result.get("web", {}).get("results", []):
        url = item.get("url", "")
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.hostname in seen:
            continue
        if not CARE.search(item.get("title", "") + " " + item.get("description", "")):
            continue
        seen.add(parsed.hostname)
        prospects.append(Prospect(item.get("title", parsed.hostname), f"https://{parsed.netloc}",
                                  discovery_source=url,
                                  notes=["Search candidate: confirm provider identity, UK registration and 50–250 employees."]))
    return prospects


def import_csv(text: str) -> list[Prospect]:
    reader = csv.DictReader(io.StringIO(text))
    if not {"company_name", "website"}.issubset(reader.fieldnames or []):
        raise PipelineError("CSV requires company_name and website columns.")
    prospects = []
    for row in reader:
        if len(prospects) >= 100:
            raise PipelineError("Import at most 100 companies at a time.")
        if not row["company_name"].strip() or not row["website"].strip():
            raise PipelineError("Every row needs a company name and website.")
        try:
            count = int(row["employee_count"]) if row.get("employee_count") else None
            if count is not None and count < 1:
                raise ValueError
        except ValueError:
            raise PipelineError("employee_count must be a positive whole number.") from None
        website = row["website"].strip().rstrip("/")
        if urlparse(website).scheme not in {"http", "https"} or not urlparse(website).hostname:
            raise PipelineError("Every website must be a full HTTP(S) URL.")
        value = lambda name, default="": (row.get(name) or default).strip()
        prospects.append(Prospect(row["company_name"].strip(), website,
                                  employee_count=count, employee_source=value("employee_source"),
                                  regulator_url=value("regulator_url"),
                                  cqc_rating=value("cqc_rating", "Unknown"),
                                  review_signal=value("review_signal", "Unknown"),
                                  cqc_source=value("cqc_source"),
                                  phone=value("phone"), phone_source=value("phone_source"),
                                  target_name=value("target_name"), target_role=value("target_role"),
                                  contact_source=value("contact_source"), linkedin_url=value("linkedin_url")))
    return prospects


def extract_contacts(soup: BeautifulSoup, source: str) -> list[tuple[str, str, str]]:
    """Conservative candidates from small team cards; human confirms identity."""
    contacts = []
    for element in soup.find_all(["article", "li", "div", "section"]):
        content = element.get_text(" ", strip=True)
        role = ROLE.search(content)
        if not role or len(content) > 500:
            continue
        headings = element.find_all(["h2", "h3", "h4", "strong"])
        for heading in headings:
            name = heading.get_text(" ", strip=True)
            if re.fullmatch(r"[A-Z][A-Za-z'’-]+(?: [A-Z][A-Za-z'’-]+){1,3}", name) and not ROLE.search(name):
                candidate = (name, role.group(0), source)
                if candidate not in contacts:
                    contacts.append(candidate)
    return contacts


def research(prospect: Prospect, reader: WebReader) -> list[tuple[str, str, str]]:
    soup = reader.page(prospect.website)
    extract_public_channels(prospect, soup, prospect.website)
    contacts = extract_contacts(soup, prospect.website)
    urls = []
    for link in soup.find_all("a", href=True):
        url = urljoin(prospect.website, link["href"]).split("#")[0]
        if (urlparse(url).hostname == urlparse(prospect.website).hostname
                and re.search(r"team|about|leadership|management", link.get_text() + " " + url, re.I)
                and url not in urls and url != prospect.website):
            urls.append(url)
    for url in urls[:4]:
        try:
            team = reader.page(url)
            contacts.extend(extract_contacts(team, url))
            extract_public_channels(prospect, team, url)
        except PipelineError as exc:
            prospect.notes.append(f"Skipped team page: {exc}")
    return list(dict.fromkeys(contacts))


def verify_contact(prospect: Prospect, key: str):
    # Clear previous results before making a fresh attempt.
    prospect.verified_email = prospect.verified_at = prospect.drafted_message = ""
    prospect.verification_status = "not_verified"
    prospect.review_status = "research"
    if not key:
        raise PipelineError("Configure HUNTER_API_KEY to find and verify corporate emails.")
    names = prospect.target_name.split()
    if len(names) < 2:
        raise PipelineError("Confirm the contact's full name first.")
    domain = urlparse(prospect.website).hostname
    if not domain:
        raise PipelineError("Company website is invalid.")
    domain = domain.removeprefix("www.")
    found = api_get("https://api.hunter.io/v2/email-finder", params={
        "domain": domain, "first_name": names[0], "last_name": " ".join(names[1:]), "api_key": key,
    }).get("data", {})
    email = found.get("email") or ""
    if "@" not in email or email.rsplit("@", 1)[1].lower() != domain.lower():
        raise PipelineError("No matching corporate-domain email found; no address was guessed.")
    verified = api_get("https://api.hunter.io/v2/email-verifier",
                       params={"email": email, "api_key": key}).get("data", {})
    if (verified.get("status") != "valid" or verified.get("result") != "deliverable"
            or verified.get("accept_all") is not False or verified.get("disposable") is not False
            or verified.get("webmail") is not False):
        prospect.verification_status = verified.get("status", "unknown")
        raise PipelineError("Email is not confirmed deliverable corporate mail; excluded from drafting.")
    prospect.verified_email = email
    prospect.verification_status = "verified"
    prospect.verified_at = datetime.now(timezone.utc).isoformat()


def eligible(prospect: Prospect) -> bool:
    return bool(not prospect.do_not_contact and prospect.employee_count is not None and 50 <= prospect.employee_count <= 250
                and prospect.employee_source.strip() and prospect.regulator_url.strip()
                and prospect.contact_source.strip() and prospect.target_name.strip()
                and ROLE.fullmatch(prospect.target_role.strip())
                and prospect.verification_status == "verified" and prospect.verified_email)


def draft(prospect: Prospect) -> str:
    if not eligible(prospect):
        raise PipelineError("Confirm target role, contact source, UK care registration, size evidence and verified email first.")
    first_name = prospect.target_name.split()[0]
    message = (
        f"Hi {first_name},\n\n"
        "This may feel like another software pitch interrupting a busy day. You likely already have "
        "core systems you have no wish to replace.\n\n"
        f"In your role as {prospect.target_role} at {prospect.company_name}, keeping compliance and HR "
        "paperwork aligned may take attention away from care. If DBS Risk Assessments and "
        "Post-Interview Induction Packs sit across separate documents, that can be especially frustrating.\n\n"
        "At 14Digital, we design bespoke recruitment trackers, HR planners and care management modules "
        "that fit around existing systems to remove those bottlenecks without disrupting current workflows.\n\n"
        "Are you opposed to exploring whether a small module could ease that administrative load?\n\n"
        "Haider Zaidi\nFounder & Director, 14Digital\nBirmingham, UK"
    )
    if len(message.split()) >= 150:
        raise PipelineError("Draft exceeds the under-150-word limit; shorten the company or role label.")
    prospect.drafted_message = message
    prospect.review_status = "pending_approval"
    return message


def handoff(prospects: list[Prospect]) -> dict:
    return {"pipeline": [{"Company Name": p.company_name, "Target Name": p.target_name,
                          "Verified Email": p.verified_email, "Drafted Message": p.drafted_message}
                         for p in prospects if p.review_status == "approved" and eligible(p)
                         and 0 < len(p.drafted_message.split()) < 150]}


def export_csv(prospects: list[Prospect]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["Company Name", "Target Name", "Verified Email", "Drafted Message"])
    writer.writeheader()
    for row in handoff(prospects)["pipeline"]:
        # Avoid spreadsheet formula execution in downloaded CSVs.
        writer.writerow({k: "'" + v if v.lstrip().startswith(("=", "+", "-", "@")) else v for k, v in row.items()})
    return output.getvalue()


def extract_public_channels(prospect: Prospect, soup: BeautifulSoup, source: str):
    for link in soup.find_all("a", href=True):
        href = link["href"].strip()
        if href.lower().startswith("tel:") and not prospect.phone:
            phone = href[4:].split("?")[0]
            if re.fullmatch(r"[+\d ()-]{7,25}", phone):
                prospect.phone, prospect.phone_source = phone, source
        parsed = urlparse(href)
        if (parsed.scheme == "https" and parsed.hostname in {"www.linkedin.com", "linkedin.com"}
                and parsed.path.startswith("/in/") and not prospect.linkedin_url):
            # Record a published link only; never scrape LinkedIn or bypass login.
            prospect.linkedin_url = href


def rank(prospect: Prospect) -> tuple[int, list[str]]:
    """Explainable business-need ranking; identity/name is never a scoring input."""
    if prospect.do_not_contact:
        return 0, ["Suppressed: do not contact"]
    score, reasons = 0, []
    if prospect.cqc_source.strip():
        points = {"inadequate": 30, "requires improvement": 20}.get(prospect.cqc_rating.strip().lower(), 0)
        if points:
            score += points
            reasons.append(f"CQC {prospect.cqc_rating}: +{points}")
        if prospect.review_signal.strip().lower() == "awaiting review":
            score += 10
            reasons.append("Documented awaiting-review signal: +10")
    if prospect.employee_count is not None and 50 <= prospect.employee_count <= 250 and prospect.employee_source.strip():
        score += 20
        reasons.append("50–250 employee fit with evidence: +20")
    if prospect.target_name.strip() and prospect.contact_source.strip() and ROLE.fullmatch(prospect.target_role.strip()):
        score += 15
        reasons.append("Relevant decision-maker with source: +15")
    if prospect.verification_status == "verified" and prospect.verified_email:
        score += 15
        reasons.append("Verified corporate email: +15")
    if prospect.regulator_url.strip():
        score += 10
        reasons.append("Regulator evidence supplied: +10")
    return score, reasons or ["More evidence needed"]


def run_batch(prospects: list[Prospect], hunter_key: str, limit: int, save, progress=None):
    """On-demand bounded research → enrichment → drafting; never approve or send."""
    if not 1 <= limit <= 50:
        raise PipelineError("Batch size must be between 1 and 50.")
    reader, completed = WebReader(), []
    candidates = sorted([p for p in prospects if not p.do_not_contact and p.review_status == "research"],
                        key=lambda p: rank(p)[0], reverse=True)[:limit]
    for index, p in enumerate(candidates):
        if progress:
            progress(index, len(candidates), p.company_name)
        try:
            if not p.target_name or not p.contact_source:
                found = research(p, reader)
                if found:
                    p.target_name, p.target_role, p.contact_source = found[0]
                    p.notes.append("Website-extracted contact candidate: confirm identity during final review.")
            research_ready = (p.employee_count is not None and 50 <= p.employee_count <= 250
                              and p.employee_source.strip() and p.regulator_url.strip()
                              and p.contact_source.strip() and p.target_name.strip()
                              and ROLE.fullmatch(p.target_role.strip()))
            if research_ready and hunter_key:
                verify_contact(p, hunter_key)
                draft(p)
            elif not research_ready:
                p.notes.append("Batch paused: size, regulator or decision-maker evidence missing.")
            else:
                p.notes.append("Batch paused: Hunter connection required for email verification.")
        except PipelineError as exc:
            p.notes.append(str(exc))
        p.notes = list(dict.fromkeys(p.notes))[-20:]
        save(p, "on_demand_batch; no automatic approval or sending")
        completed.append(p)
    return completed


RESEARCH_FIELDS = ["company_name", "website", "employee_count", "employee_source", "regulator_url",
                   "cqc_rating", "review_signal", "cqc_source", "target_name", "target_role",
                   "contact_source", "phone", "phone_source", "linkedin_url"]


def research_csv(prospects: list[Prospect]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=RESEARCH_FIELDS + ["priority_score", "ranking_reasons", "do_not_contact"])
    writer.writeheader()
    for p in sorted(prospects, key=lambda p: rank(p)[0], reverse=True):
        score, reasons = rank(p)
        row = {k: getattr(p, k) for k in RESEARCH_FIELDS}
        row.update(priority_score=score, ranking_reasons="; ".join(reasons), do_not_contact=p.do_not_contact)
        writer.writerow({k: "'" + v if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@")) else v for k, v in row.items()})
    return output.getvalue()
