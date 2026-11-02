"""Run with: streamlit run app.py"""
import json
import os
from urllib.parse import quote_plus

import streamlit as st

from prospectsz.pipeline import (PipelineError, WebReader, discover, draft, eligible,
                                 export_csv, handoff, import_csv, research,
                                 is_directory_url, rank, research_csv, run_batch, RESEARCH_FIELDS)
from prospectsz.store import Store

st.set_page_config(page_title="ProspectSZ · 14Digital", page_icon="◈", layout="wide")

DEFAULT_GOOGLE_SEARCH_ENGINE_ID = "86e430f9380d94ea2"


def key(name):
    value = os.getenv(name, "")
    if value:
        return value
    try:
        value = st.secrets.get(name, "")
        if value:
            return value
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        pass
    if name == "GOOGLE_SEARCH_API_KEY":
        return st.session_state.get("google_api_key_session", "")
    if name == "GOOGLE_SEARCH_ENGINE_ID":
        return DEFAULT_GOOGLE_SEARCH_ENGINE_ID
    return ""


store = Store()
prospects = store.all()
with st.sidebar:
    st.title("14Digital")
    st.caption("PROSPECTSZ / SALES OPERATIONS")
    page = st.radio("Workspace", ["Command centre", "Discover & import", "Research & enrich", "Approval queue", "Export & audit"])
    st.divider()
    st.caption("UK regulated care · 50–250 employees")
    st.text_input("Google API key", type="password", key="google_api_key_session",
                  help="Used only for this browser session and sent only to Google's Custom Search API.")
    google_ready = bool(key("GOOGLE_SEARCH_API_KEY") and key("GOOGLE_SEARCH_ENGINE_ID"))
    st.write("Google Search: " + ("configured" if google_ready else "manual mode"))
    st.caption("The session key is not written to the database or repository. Environment secrets remain supported.")

st.title(page)
st.caption("From public business research to thoughtful outreach — every message reviewed by a person.")

if page == "Command centre":
    cols = st.columns(4)
    for col, label, value in zip(cols, ["Companies", "Verified contacts", "Awaiting review", "Approved"], [
        len(prospects), sum(p.verification_status in {"verified", "source_confirmed"} for p in prospects),
        sum(p.review_status == "pending_approval" for p in prospects), sum(p.review_status == "approved" for p in prospects)]):
        col.metric(label, value)
    st.subheader("Your pipeline")
    if prospects:
        st.dataframe([{"Priority": rank(p)[0], "Company": p.company_name, "CQC": p.cqc_rating,
                       "Website": p.website, "Contact": p.target_name, "Public phone": p.phone,
                       "Email status": p.verification_status, "Review": p.review_status,
                       "Why ranked": "; ".join(rank(p)[1])} for p in sorted(prospects, key=lambda p: rank(p)[0], reverse=True)], hide_index=True)
    else:
        st.info("Start in Discover & import. Search for care providers or upload your company shortlist.")
    st.subheader("How the workflow works")
    st.write("1. Discover candidates → 2. Confirm provider and size evidence → 3. Research decision-makers → "
             "4. Verify corporate email → 5. Draft → 6. Human approval → 7. Export")
    st.info("This application drafts and exports only. It has no email or LinkedIn sending capability. "
            "Search results and extracted names are candidates until you confirm the evidence.")
    st.subheader("Run today's shortlist")
    limit = st.slider("Maximum companies to process this run", 1, 50, 40)
    st.caption("One contact per company. Processes research-stage records in priority order, skips suppressed and already-drafted records. "
               "Thirty to fifty is a target, not a guaranteed number of verified contacts. No scheduled background runs.")
    if st.button("Research, verify & draft this batch", disabled=not bool(prospects)):
        meter = st.progress(0.0)
        label = st.empty()
        def update(index, total, company):
            meter.progress(index / max(total, 1))
            label.write(f"Researching {index + 1}/{total}: {company}")
        processed = run_batch(prospects, limit, store.save, update)
        meter.progress(1.0)
        st.success(f"Processed {len(processed)} companies; {sum(p.review_status == 'pending_approval' for p in processed)} drafts queued. "
                   "Check research notes for incomplete records.")
    st.subheader("Calling handoff")
    st.write("Public business numbers are collected with their source for human review. Calling is not connected. "
             "A future dialler must use an authorised number, honour suppression and identify automation honestly.")
    st.code("Hello, this is [name] from 14Digital in Birmingham. Have I caught you at a bad time? "
            "We build small care administration modules around existing systems. Who looks after your operations or recruitment processes?", language=None)

elif page == "Discover & import":
    query = st.text_input("UK care provider search", 'care provider "requires improvement"')
    search_limit = st.slider("Google results to inspect", 10, 50, 40, step=10)
    st.link_button("Open this search in Google", "https://www.google.com/search?q=" + quote_plus(query))
    google_ready = bool(key("GOOGLE_SEARCH_API_KEY") and key("GOOGLE_SEARCH_ENGINE_ID"))
    if st.button("Import Google results automatically", disabled=not google_ready):
        try:
            with st.spinner("Searching public business sources…"):
                found = discover(query, key("GOOGLE_SEARCH_API_KEY"), key("GOOGLE_SEARCH_ENGINE_ID"), search_limit)
                existing = {p.website for p in prospects}
                for p in found:
                    if p.website not in existing:
                        store.save(p, "discovered")
                        existing.add(p.website)
            st.success(f"Found {len(found)} candidates. Review them in Research & enrich.")
            if not found:
                st.warning("Google returned no matching listings. Try a broader query such as `care provider`.")
        except PipelineError as exc:
            st.error(str(exc))
    st.subheader("Import a shortlist")
    st.caption("Use CQC as your starting source: import company websites alongside CQC ratings and source links. "
               "Awaiting review must be documented explicitly; an old inspection date alone does not establish that status. "
               "Clay/Prospect can exchange the same CSV; no direct account connection is assumed.")
    st.download_button("Download CSV template", ",".join(RESEARCH_FIELDS) + "\n", "companies-template.csv", "text/csv")
    uploaded = st.file_uploader("Company CSV (up to 100 rows)", type="csv")
    update_existing = st.checkbox("Update matching websites with non-empty research fields (clears previous verification, draft and approval)")
    if uploaded and st.button("Import companies"):
        try:
            imported = import_csv(uploaded.getvalue().decode("utf-8-sig"))
            existing = {p.website: p for p in prospects}
            added, updated = 0, 0
            for p in imported:
                if p.website not in existing:
                    store.save(p, "imported")
                    existing[p.website] = p
                    added += 1
                elif update_existing:
                    previous = existing[p.website]
                    for field in RESEARCH_FIELDS:
                        value = getattr(p, field)
                        if value not in (None, "", "Unknown"):
                            setattr(previous, field, value)
                    previous.verified_at = previous.drafted_message = ""
                    previous.verification_status = ("source_confirmed" if previous.verified_email and previous.email_source else "not_checked")
                    previous.review_status = "research"
                    store.save(previous, "CSV research updated; verification and approval cleared")
                    updated += 1
            st.success(f"Imported {added} new companies; updated {updated} matching records.")
        except (PipelineError, UnicodeDecodeError) as exc:
            st.error(str(exc))

elif page == "Research & enrich":
    if not prospects:
        st.info("Discover or import companies first.")
    else:
        selected = st.selectbox("Company", prospects, format_func=lambda p: p.company_name)
        p = selected
        st.write(p.website)
        st.caption("Discovery source: " + p.discovery_source)
        st.warning("Confirm this is a UK regulated care provider with 50–250 employees. "
                   "Use the relevant regulator (CQC, CIW, Care Inspectorate Scotland or RQIA) and a dated headcount source. "
                   "The app does not infer registration or employee count from search snippets.")
        if is_directory_url(p.website):
            st.info("This is a directory listing. Find the provider's official website in Google, save it below, then scan its team pages.")
            official_site = st.text_input("Official company website", placeholder="https://provider.example")
            if st.button("Save official website"):
                from urllib.parse import urlparse
                parsed = urlparse(official_site.strip())
                if parsed.scheme != "https" or not parsed.hostname or is_directory_url(official_site.strip()):
                    st.error("Enter the provider's full official HTTPS website URL.")
                else:
                    old_website = p.website
                    p.website = official_site.strip().rstrip("/")
                    p.notes.append(f"Official website manually confirmed from listing: {p.discovery_source}")
                    store.delete(old_website)
                    store.save(p, "official website confirmed; directory candidate re-keyed")
                    st.rerun()
        if st.button("Scan public team pages", disabled=is_directory_url(p.website)):
            try:
                with st.spinner("Reading up to five pages, respecting robots.txt and crawl delays…"):
                    candidates = research(p, WebReader())
                st.session_state["candidates:" + p.website] = candidates
                store.save(p, "website_researched")
                if not candidates:
                    st.info("No reliable team-card candidate found. Enter a contact and source manually.")
            except PipelineError as exc:
                st.error(str(exc))
        candidates = st.session_state.get("candidates:" + p.website, [])
        if candidates:
            st.dataframe([{"Name candidate": c[0], "Role": c[1], "Source": c[2]} for c in candidates], hide_index=True)
        with st.form("evidence:" + p.website):
            company = st.text_input("Confirmed company name", p.company_name)
            count = st.number_input("Employee count", min_value=0, value=p.employee_count or 0)
            employee_source = st.text_input("Headcount evidence URL and date", p.employee_source)
            regulator = st.text_input("UK regulator registration URL (confirm manually)", p.regulator_url)
            name = st.text_input("Confirmed decision-maker full name", p.target_name)
            roles = ["Operations Director", "Director of Operations", "Registered Manager", "Managing Director", "Owner", "Founder"]
            role = st.selectbox("Confirmed role", roles,
                                index=([r.lower() for r in roles].index(p.target_role.lower())
                                       if p.target_role.lower() in [r.lower() for r in roles] else 0))
            source = st.text_input("Contact evidence URL", p.contact_source)
            ratings = ["Unknown", "Inadequate", "Requires improvement", "Good", "Outstanding", "Not yet rated"]
            rating = st.selectbox("CQC overall rating", ratings, index=ratings.index(p.cqc_rating) if p.cqc_rating in ratings else 0)
            signals = ["Unknown", "Awaiting review", "No documented signal"]
            signal = st.selectbox("Documented review status", signals, index=signals.index(p.review_signal) if p.review_signal in signals else 0)
            cqc_source = st.text_input("CQC rating / review evidence URL and checked date", p.cqc_source)
            phone = st.text_input("Public business telephone", p.phone)
            phone_source = st.text_input("Telephone source URL", p.phone_source)
            linkedin_url = st.text_input("Published LinkedIn profile link (no LinkedIn scraping)", p.linkedin_url)
            suppressed = st.checkbox("Do not contact this company", p.do_not_contact)
            confirmed = st.checkbox("I have checked the provider, headcount, person and role against these sources.")
            if st.form_submit_button("Save confirmed research"):
                if not confirmed or not all([company.strip(), count, employee_source.strip(), regulator.strip(), name.strip(), source.strip()]):
                    st.error("Complete the evidence fields and confirmation.")
                else:
                    p.company_name, p.employee_count, p.employee_source = company.strip(), int(count), employee_source.strip()
                    p.regulator_url, p.target_name, p.target_role, p.contact_source = regulator.strip(), name.strip(), role, source.strip()
                    p.cqc_rating, p.review_signal, p.cqc_source = rating, signal, cqc_source.strip()
                    p.phone, p.phone_source, p.linkedin_url = phone.strip(), phone_source.strip(), linkedin_url.strip()
                    p.do_not_contact = suppressed
                    p.verified_email = p.verified_at = p.email_source = p.drafted_message = ""
                    p.verification_status, p.review_status = "not_checked", "research"
                    store.save(p, "research_confirmed; previous verification and approval cleared")
                    st.success("Research saved. Verify the email next.")
        st.subheader("Email evidence")
        st.caption("Use Google to locate the official team/contact page. A company-published address can be source-confirmed, "
                   "but Google does not verify deliverability.")
        email = st.text_input("Target's corporate email", p.verified_email)
        email_source = st.text_input("Official webpage showing that email", p.email_source)
        email_checked = st.checkbox("I confirmed this address belongs to the target and appears on the official company website.")
        if st.button("Save source-confirmed email"):
            domain = p.website.split("//", 1)[-1].split("/", 1)[0].removeprefix("www.").lower()
            email_domain = email.rsplit("@", 1)[-1].lower() if "@" in email else ""
            if not email_checked or not email_source.startswith("https://") or email_domain != domain:
                st.error("Confirm an HTTPS official source and an email on the exact company website domain.")
            else:
                p.verified_email, p.email_source = email.strip(), email_source.strip()
                p.verification_status, p.verified_at = "source_confirmed", ""
                p.drafted_message, p.review_status = "", "research"
                store.save(p, "official-site email source confirmed; deliverability not verified")
                st.success("Email saved as publicly sourced. Deliverability remains unverified.")
        st.write("Email status: " + p.verification_status)
        st.write(f"Priority: {rank(p)[0]}/100 — " + "; ".join(rank(p)[1]))
        if st.button("Suppress company from outreach", key="suppress:" + p.website):
            p.do_not_contact, p.review_status = True, "suppressed"
            store.save(p, "do_not_contact")
            st.rerun()
        if st.button("Draft outreach for review", disabled=not eligible(p)):
            try:
                draft(p)
                store.save(p, "draft_created; pending human approval")
                st.success("Draft is in the approval queue.")
            except PipelineError as exc:
                st.error(str(exc))
        if p.notes:
            st.caption(" · ".join(p.notes))
        if st.checkbox("Show deletion controls"):
            if st.button("Delete this company and its local audit records"):
                store.delete(p.website)
                st.rerun()

elif page == "Approval queue":
    queue = [p for p in prospects if p.drafted_message]
    if not queue:
        st.info("No drafts yet. Confirm research and verify an email to create one.")
    for p in queue:
        with st.expander(f"{p.company_name} · {p.review_status}", expanded=True):
            st.write(f"{p.target_name} · {p.target_role} · {p.verified_email}")
            st.caption(f"Email status: {p.verification_status}. Email source: {p.email_source}. Contact source: {p.contact_source}")
            message = st.text_area("Draft", p.drafted_message, key="message:" + p.website, height=300)
            st.caption(f"{len(message.split())} words · required sequence: accusation audit, empathy, solution, no-oriented close.")
            reviewed = st.checkbox("I have reviewed the evidence, wording and suitability for outreach.", key="review:" + p.website)
            a, b, c = st.columns(3)
            if a.button("Save revision", key="save:" + p.website):
                p.drafted_message, p.review_status = message, "pending_approval"
                store.save(p, "draft_edited; approval cleared")
                st.rerun()
            if b.button("Approve for export", key="approve:" + p.website):
                if not reviewed or not eligible(p) or not 0 < len(message.split()) < 150:
                    st.error("Review confirmation, verified eligibility and a draft under 150 words are required.")
                else:
                    p.drafted_message, p.review_status = message, "approved"
                    store.save(p, "human_approved")
                    st.rerun()
            if c.button("Reject", key="reject:" + p.website):
                p.review_status = "rejected"
                store.save(p, "human_rejected")
                st.rerun()

elif page == "Export & audit":
    output = handoff(prospects)
    st.write(f"{len(output['pipeline'])} approved contacts ready for handoff.")
    st.json(output)
    st.download_button("Download approved JSON", json.dumps(output, indent=2), "14digital-approved.json", "application/json")
    st.download_button("Download approved CSV", export_csv(prospects), "14digital-approved.csv", "text/csv")
    st.caption("Exports contain approved records only. Rejected, unverified and pending records are excluded. Nothing is sent.")
    st.subheader("Clay / Prospect research exchange")
    st.download_button("Download ranked research CSV", research_csv(prospects), "14digital-research.csv", "text/csv")
    st.caption("Research export includes unverified candidates and suppression flags. It is for enrichment, not an approved sending list. "
               "Bring enriched fields back through Discover & import; emails require an official company-page source.")
    st.subheader("Local activity log")
    st.dataframe(store.audit(), hide_index=True)
