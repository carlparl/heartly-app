# Heartly production email configuration

Configure these variables in the Render service dashboard.

## Brevo SMTP example

```text
DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
DJANGO_EMAIL_HOST=smtp-relay.brevo.com
DJANGO_EMAIL_PORT=587
DJANGO_EMAIL_HOST_USER=<your Brevo SMTP login>
DJANGO_EMAIL_HOST_PASSWORD=<your Brevo SMTP key>
DJANGO_EMAIL_USE_TLS=true
DJANGO_EMAIL_USE_SSL=false
DJANGO_DEFAULT_FROM_EMAIL=Heartly <verified-sender@your-domain.com>
DJANGO_EMAIL_TIMEOUT=20
```

Never commit SMTP credentials to GitHub.

## Verify delivery before enforcement

```powershell
python manage.py check_email_delivery
python manage.py check_email_delivery --send --to your-real-email@example.com
```

The first command only inspects configuration. The second sends one test.

## Enable verified-email enforcement

Only after verification and password-reset emails arrive correctly:

```text
HEARTLY_REQUIRE_VERIFIED_EMAIL=true
```

To disable the gate:

```text
HEARTLY_REQUIRE_VERIFIED_EMAIL=false
```
