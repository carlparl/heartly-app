from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_reviewed_status(apps, schema_editor):
    PostReport = apps.get_model("feed", "PostReport")
    PostReport.objects.filter(reviewed=True).update(
        status="reviewed"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("feed", "0010_story_reaction"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="post",
            name="hidden_by_moderation",
            field=models.BooleanField(
                db_index=True,
                default=False,
            ),
        ),
        migrations.AddField(
            model_name="post",
            name="moderation_note",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="post",
            name="moderated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="post",
            name="moderated_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="moderated_feed_posts",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="postreport",
            name="moderator_note",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="postreport",
            name="reviewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="postreport",
            name="reviewed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="reviewed_feed_post_reports",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="postreport",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("reviewed", "Reviewed"),
                    ("actioned", "Action taken"),
                    ("dismissed", "Dismissed"),
                ],
                default="pending",
                max_length=20,
            ),
        ),
        migrations.RunPython(
            backfill_reviewed_status,
            migrations.RunPython.noop,
        ),
    ]
