# ProspectSZ · 14Digital

A local Streamlit command centre for researching UK regulated care providers with 50–250 employees, verifying decision-maker emails and reviewing outreach drafted on behalf of Haider Zaidi. No messages are sent by this application.

## Run

Python 3.12 is the tested runtime.

Streamlit Community Cloud should use Python 3.12. The repository includes both `runtime.txt` and `.python-version`; when creating the app, choose Python 3.12 under Advanced settings if the deployment form offers a runtime selector.

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/streamlit run app.py --server.address 127.0.0.1
```

Run from the repository root. SQLite data is stored in ignored `data/pipeline.sqlite3`. Set `PROSPECTSZ_DB` to select another local path. Live processes must be restarted after restoring a cloud environment.

## Integrations

Set these environment variables, or put them in the ignored `.streamlit/secrets.toml`:

```toml
GOOGLE_SEARCH_API_KEY = "your-key"
GOOGLE_SEARCH_ENGINE_ID = "your-programmable-search-engine-id"
```

Discovery opens an ordinary Google search for human review. Paste selected results into the app as `Company Name | https://official-website` lines, or upload the research CSV template. This avoids scraping Google and does not require or store a Google API key. Public provider websites must be reachable. Never commit contact exports.

## Workflow

1. Search Google and paste up to 100 reviewed `Company | URL` results into the app, or import a UTF-8 CSV using the downloadable research template. Search results are unqualified candidates; confirm the company website manually.
2. Scan public team pages (at most five per company). The crawler honours robots.txt, spaces requests, limits response sizes and rejects private network destinations. If robots permissions cannot be established, use manual research. Extraction supports simple team cards; JavaScript-only websites need manual research. A discovered name is a candidate, not an asserted identity.
3. Confirm the company, relevant UK regulator listing (CQC, CIW, Care Inspectorate Scotland or RQIA), 50–250 employee count with dated evidence, Operations Director or Registered Manager name, role and contact source. These facts require human evidence review; the app does not automatically verify company size or registration. Never invent missing facts.
4. Use Google to locate an email published on the official company website. Confirm the exact company domain and save the source page. The app labels this `source_confirmed`: it establishes provenance, not deliverability. Do not guess addresses.
5. Generate a deterministic, personalised draft under 150 words: accusation audit, tactical empathy, bespoke modules around existing systems, then a no-oriented question. Administrative problems are phrased conditionally; no company-specific pain is claimed without evidence. No language-model API is required.
6. Edit, approve or reject each draft. Saving revisions clears approval. Editing research clears email verification and the draft. Approval records an explicit human review; it never sends anything.
7. Download approved records as JSON or CSV, with `Company Name`, `Target Name`, `Verified Email`, `Drafted Message`. Pending, rejected and ineligible records are excluded. CSV cells are protected against formula execution.

The command centre can run a bounded, on-demand batch of up to 50 research-stage companies. It ranks records using documented CQC need signals, 50–250 employee fit, role relevance, regulator evidence and contact verification. Names, perceived ethnicity and other protected characteristics never affect ranking. The score is a research priority, not a claim that a provider is suitable or likely to buy.

The ranked research CSV is designed as a neutral interchange with Clay or another prospecting tool. Re-importing matching websites can update non-empty research fields and deliberately clears older verification, drafts and approval. Direct Clay/API integration is not enabled until the exact product, account method and field mapping are known.

The local audit records research, verification attempts and approval actions. Delete a company in Research & enrich to remove its record and local audit. Downloaded copies must be managed separately. This is a single-operator application without login or multi-user access controls: keep it on loopback or behind authenticated infrastructure. Maintain your organisation's contact retention and suppression process before acting on exports.

## Validation

```bash
.venv/bin/python -m unittest discover -s tests -v
curl --fail http://127.0.0.1:8501/_stcore/health
```

Tests cover Google result handling, eligibility and approval gates, email-source handling, drafting, CSV safety, local-address rejection, persistence, and Streamlit page startup. Real Google and provider-website requests require configured access and must be validated separately. No sample contact is presented as a real or verified prospect.
