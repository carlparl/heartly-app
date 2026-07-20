# Heartly Phases 27–30 deployment checklist

This release adds bounded high-traffic collections, production query indexes,
shared accessibility improvements, privacy-preserving runtime counters, and a
final release-candidate gate.

## Database changes

Apply the generated accounts, profiles, chat, and notifications index
migrations. They add indexes only; they do not rewrite member content.

## Pre-deploy

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --plan
python manage.py test
python manage.py audit_accessibility_readiness --fail-on-issues
```

The performance audit must run after the new indexes are applied.

## Deploy

1. Keep `USE_REDIS_CACHE=True` and the existing production Redis connection.
2. Apply migrations before switching traffic to the new application version:

   ```bash
   python manage.py migrate accounts 0007
   python manage.py migrate profiles 0012
   python manage.py migrate chat 0011
   python manage.py migrate notifications 0004
   ```

3. Verify `/health/live/` and `/health/ready/` return HTTP 200.
4. Run `audit_performance_readiness --fail-on-issues`.
5. Run `audit_release_candidate --fail-on-issues` and save its JSON report.
6. Let production traffic create an adequate runtime sample, then rerun
   `audit_runtime_health --fail-on-issues`.
7. Have authorized adult staff perform keyboard-only, zoom, screen-reader,
   moderation, and restricted-account checks.

## Operational commands

```bash
python manage.py audit_runtime_health --hours 2
python manage.py audit_performance_readiness
python manage.py audit_accessibility_readiness
python manage.py audit_release_candidate --fail-on-issues
```

Runtime counters are aggregate Redis values. They contain no route, user,
query-string, or request-body data and expire automatically.

## Rollback

Deploy commit `1606335` as the preceding known-good application version. The
new indexes are backward compatible and may remain in place during application
rollback. Do not roll back by deleting member data, safety reports, evidence,
or moderation history.
