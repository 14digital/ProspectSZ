# 14Digital Sales Outreach Agent

A production-oriented, human-in-the-loop system for UK B2B prospect discovery, evidence-led qualification, contact research, compliant drafting, approval, sending and follow-up. CQC CSV data is the dependable discovery source; Google Custom Search is not required.

## Architecture

- `apps/web`: Next.js and TypeScript operator console with Dashboard, Discovery, Prospects, Outreach Studio, Follow-ups and Settings.
- `services/api`: FastAPI, SQLAlchemy, Alembic and a PostgreSQL-backed durable worker queue.
- PostgreSQL stores companies, locations, identifiers, evidence, contacts, scores, compliance decisions, immutable revisions, approvals, messages, sequences, tasks, pipeline activity and audits.
- Provider interfaces isolate Companies House, OpenAI and email. Email defaults to `mock`; live SMTP requires credentials and `LIVE_EMAIL_ENABLED=true`.

## Local startup

1. Copy `.env.example` to `.env` and replace the passwords and application secret.
2. Run `docker compose up --build`.
3. Open `http://localhost:3000` and sign in with `ADMIN_EMAIL` and `ADMIN_PASSWORD`.

The loopback API is at `http://localhost:8000`; documentation is at `/api/docs`. Startup runs Alembic and creates the configured admin if absent. The worker leases jobs with expiry and bounded retries, so work survives restarts.

For development without Docker:

```bash
python -m venv .venv
.venv/bin/pip install -r services/api/requirements.txt
cd services/api && PYTHONPATH=. ../../.venv/bin/alembic upgrade head
PYTHONPATH=. ../../.venv/bin/uvicorn app.main:app --reload

cd apps/web && npm ci && npm run dev
```

## Operator workflow

1. Create a Discovery run and upload the official CQC provider/location CSV. Imports are hashed, deduplicated, attributed and asynchronous. Bad rows retain rejection reasons; malformed files fail visibly.
2. Verify the legal entity with Companies House, capture website evidence, add source-attributed contacts and calculate the deterministic score.
3. Record subscriber type, legal-entity evidence, lawful basis and privacy notice. Unknown or incomplete assessments block sending.
4. Create or AI-generate a draft. AI output is validated and stored pending review; source text is treated as untrusted data. Edit, approve and send are separate actions. Any edit invalidates approval.
5. The final send gate rechecks approval, revision, corporate eligibility and suppression. LinkedIn remains manual. Replies and opt-outs stop pending sequences.

The app never guesses emails. A contact needs a public source URL and an explicit verification state. Missing research lowers confidence and appears in scoring explanations rather than becoming assumed fact.

## Configuration

Keep secrets in environment variables and out of Git. Companies House and OpenAI are optional. `EMAIL_PROVIDER=mock` records simulated sends. For authorised SMTP, set `EMAIL_PROVIDER=smtp`, the `SMTP_*` variables and deliberately set `LIVE_EMAIL_ENABLED=true`.

The Google error `This project does not have the access to Custom Search JSON API` comes from Google Cloud. The project owning that key cannot call the legacy API. This rebuild avoids the dependency through CQC imports. If a separate Google integration is retained, enable the API in the exact key-owning project, attach billing if required and permit the API in key restrictions.

## Validation

```bash
cd services/api && PYTHONPATH=. ../../.venv/bin/pytest -q
cd apps/web && npm test && npm run build
docker compose config
```

Tests cover authentication, migration presence, CQC grouping and deduplication, malformed input, deterministic evidence scoring, missing data, durable job leasing, follow-up stopping, approval invalidation, compliance and suppression gates, and send idempotency.

See [operations.md](docs/operations.md) for backup, restore, deployment and incident checks, and [data-governance.md](docs/data-governance.md) for retention, subject requests and suppression handling.
