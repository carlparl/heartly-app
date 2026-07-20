from django.db import migrations, models
from django.utils import timezone


def backfill_profile_evidence(apps, schema_editor):
    Profile = apps.get_model("profiles", "Profile")
    ProfileReport = apps.get_model("profiles", "ProfileReport")
    captured_at = timezone.now().isoformat()
    for report in ProfileReport.objects.all().iterator():
        profile = Profile.objects.filter(
            user_id=report.reported_user_id
        ).first()
        report.evidence_snapshot = {
            "schema_version": 1,
            "kind": "profile",
            "captured_at": captured_at,
            "reported_user_id": report.reported_user_id,
            "display_name": (
                (profile.display_name or "")[:120]
                if profile
                else ""
            ),
            "bio": (
                (profile.bio or "")[:2000]
                if profile
                else ""
            ),
            "location": (
                (profile.location or "")[:120]
                if profile
                else ""
            ),
        }
        report.save(update_fields=["evidence_snapshot"])


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0006_customuser_moderation_state"),
        ("profiles", "0010_moderationaction"),
    ]

    operations = [
        migrations.AddField(
            model_name="profilereport",
            name="evidence_snapshot",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name="moderationaction",
            name="action",
            field=models.CharField(
                choices=[
                    ("report_reviewed", "Report reviewed"),
                    ("report_actioned", "Report actioned"),
                    ("report_dismissed", "Report dismissed"),
                    ("profile_hidden", "Profile hidden"),
                    ("profile_restored", "Profile restored"),
                    ("post_hidden", "Post hidden"),
                    ("post_restored", "Post restored"),
                    ("account_suspended", "Account suspended"),
                    ("account_banned", "Account banned"),
                    ("account_restored", "Account restored"),
                ],
                max_length=40,
            ),
        ),
        migrations.AlterField(
            model_name="moderationaction",
            name="source_type",
            field=models.CharField(
                choices=[
                    ("profile", "Profile"),
                    ("profile_report", "Profile report"),
                    ("post", "Post"),
                    ("post_report", "Post report"),
                    ("chat_report", "Chat report"),
                    ("account", "Account"),
                ],
                max_length=40,
            ),
        ),
        migrations.RunPython(
            backfill_profile_evidence,
            migrations.RunPython.noop,
        ),
    ]
