# Operations runbook

Before release, run backend tests, the frontend production build and `docker compose config`. Back up PostgreSQL before migration. Deploy immutable images, run `alembic upgrade head`, and verify `/health`, sign-in, a mock email, a CQC import and worker completion before enabling live email.

Create an encrypted backup from a trusted host:

```bash
docker compose exec -T db pg_dump -U prospectsz -Fc prospectsz > prospectsz.dump
```

Test restoration regularly in an isolated database with `pg_restore --clean --if-exists --no-owner`. Protect backups with restricted access, encryption and the production retention schedule.

If sending is unexpected, disable `LIVE_EMAIL_ENABLED` first. Preserve audit events and provider IDs. Review failed jobs, suppression state and the approved revision. Rotate affected credentials, reconcile provider records and document corrective action before restoring service.
