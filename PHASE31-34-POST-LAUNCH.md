# Heartly phases 31–34 post-launch closeout

This bundle completes a finite post-launch roadmap:

- Phase 31: strict, evidence-based production closeout.
- Phase 32: authenticated account-data export and privacy audit.
- Phase 33: aggregate rate-limit monitoring and integrity coverage audit.
- Phase 34: combined post-launch certification and operator handoff.

## Truthful recovery evidence

Do not set recovery values merely to make an audit pass. An authorized operator
must first verify the actual backup service, store the real runbook in an
approved location, and complete a documented restore drill.

Only then configure production values such as:

```text
HEARTLY_BACKUP_PROVIDER=<verified provider and plan>
HEARTLY_RECOVERY_RUNBOOK_REFERENCE=<real controlled document reference>
HEARTLY_LAST_RECOVERY_DRILL_AT=<real ISO-8601 completion timestamp>
```

## Production closeout

Run from the Render service environment so the command sees production Redis,
the production database, and real runtime samples:

```bash
python manage.py audit_runtime_health --hours 2 --fail-on-warnings
python manage.py audit_integrity_health --hours 2
python manage.py audit_production_closeout --runtime-hours 2 --fail-on-issues
python manage.py audit_post_launch_readiness --runtime-hours 2 --fail-on-issues
```

The two closeout commands are read-only. They do not create backup evidence or
change database records.

## Account-data export

The export requires an authenticated session, the account password when one
exists, the exact confirmation word, CSRF protection, and the sensitive-account
rate limit. It excludes credentials, internal evidence snapshots, staff notes,
and other members' private account information. Each collection is bounded and
explicitly marks truncation.

## Manual sign-off

Authorized adult staff should complete keyboard, zoom, screen-reader,
moderation, account-restriction, data-export, and recovery-runbook checks. Do
not use synthetic results as evidence of a real production restore drill.
