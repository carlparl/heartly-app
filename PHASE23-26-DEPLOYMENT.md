# Heartly Phases 23–26 deployment checklist

This release adds session and request security, shared abuse throttling,
operational-data retention, service health probes, recovery monitoring, and an
aggregate launch gate. It contains no schema migration.

## Required production configuration

- Keep `DJANGO_ENV=production`, `DJANGO_DEBUG=False`, `REDIS_URL`, and
  `USE_REDIS_CHANNEL_LAYER=True`.
- Set `USE_REDIS_CACHE=True` so HTTP and WebSocket limits are shared across
  processes.
- Keep `HEARTLY_TRUST_X_FORWARDED_FOR=True` only behind Render or another
  trusted proxy that replaces the forwarded client address.
- Document the real backup provider in `HEARTLY_BACKUP_PROVIDER`.
- Set `HEARTLY_RECOVERY_RUNBOOK_REFERENCE` to the internal recovery procedure.
- Set `HEARTLY_LAST_RECOVERY_DRILL_AT` only after an authorized operator has
  completed and verified a real restore drill. Use an ISO-8601 timestamp.

## Pre-deploy

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --plan
python manage.py test
python manage.py audit_operational_readiness --fail-on-issues
python manage.py audit_launch_gate --fail-on-issues
```

Recovery documentation and cleanup status can be enforced separately with
`--fail-on-warnings` after those operational tasks are complete.

## Deploy and verify

1. Deploy the tested commit through the normal Render service.
2. Confirm `/health/live/` and `/health/ready/` return HTTP 200.
3. Confirm the homepage, login, signup, public policy pages, and `/sw.js`
   return HTTP 200.
4. Run `audit_launch_gate` against the production database and save its JSON
   report.
5. Have authorized adult staff verify moderation and restricted-account flows.

## Scheduled operations

- Run `audit_launch_gate --fail-on-issues` at least daily.
- Run `audit_data_retention` before cleanup.
- Run `prune_expired_operational_data --apply` on an approved schedule.
- Keep moderation evidence and audit tables outside automated retention.
- Complete and document a restore drill at least every 90 days.

## Rollback

This release has no schema change. If application rollback is required, deploy
the preceding known-good commit through Render. Keep Redis and database data in
place, then rerun `/health/ready/` and the aggregate launch gate. Do not erase
moderation evidence or audit history during rollback.
