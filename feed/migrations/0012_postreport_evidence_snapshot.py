from django.db import migrations, models
from django.utils import timezone


def backfill_post_evidence(apps, schema_editor):
    PostReport = apps.get_model("feed", "PostReport")
    captured_at = timezone.now().isoformat()
    for report in PostReport.objects.select_related("post").iterator():
        post = report.post
        media_types = []
        if post.image:
            media_types.append("image")
        if post.video:
            media_types.append("video")
        report.evidence_snapshot = {
            "schema_version": 1,
            "kind": "post",
            "captured_at": captured_at,
            "post_id": post.id,
            "author_id": post.author_id,
            "content": (post.content or "")[:4000],
            "media_types": media_types,
            "created_at": post.created_at.isoformat(),
            "edited_at": (
                post.edited_at.isoformat()
                if post.edited_at
                else None
            ),
        }
        report.save(update_fields=["evidence_snapshot"])


class Migration(migrations.Migration):
    dependencies = [
        ("feed", "0011_moderation_workflow"),
    ]

    operations = [
        migrations.AddField(
            model_name="postreport",
            name="evidence_snapshot",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.RunPython(
            backfill_post_evidence,
            migrations.RunPython.noop,
        ),
    ]
