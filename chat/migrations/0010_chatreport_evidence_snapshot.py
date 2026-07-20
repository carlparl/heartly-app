from django.db import migrations, models
from django.utils import timezone


def backfill_chat_evidence(apps, schema_editor):
    ChatAttachment = apps.get_model("chat", "ChatAttachment")
    ChatMessage = apps.get_model("chat", "ChatMessage")
    ChatReport = apps.get_model("chat", "ChatReport")
    captured_at = timezone.now().isoformat()
    for report in ChatReport.objects.all().iterator():
        messages = list(
            ChatMessage.objects.filter(thread_id=report.thread_id)
            .order_by("-created_at", "-id")[:20]
        )
        messages.reverse()
        message_ids = [message.id for message in messages]
        attachments_by_message = {
            message_id: [] for message_id in message_ids
        }
        for attachment in ChatAttachment.objects.filter(
            message_id__in=message_ids
        ).iterator():
            attachments_by_message[attachment.message_id].append(
                {
                    "type": attachment.attachment_type,
                    "content_type": (
                        attachment.content_type or ""
                    )[:120],
                    "original_filename": (
                        attachment.original_filename or ""
                    )[:255],
                    "file_size": attachment.file_size,
                    "duration_seconds": (
                        attachment.duration_seconds
                    ),
                }
            )
        report.evidence_snapshot = {
            "schema_version": 1,
            "kind": "chat",
            "captured_at": captured_at,
            "thread_id": report.thread_id,
            "reported_user_id": report.reported_user_id,
            "messages": [
                {
                    "message_id": message.id,
                    "sender_id": message.sender_id,
                    "text": (message.text or "")[:1200],
                    "created_at": message.created_at.isoformat(),
                    "attachments": attachments_by_message[
                        message.id
                    ],
                }
                for message in messages
            ],
        }
        report.save(update_fields=["evidence_snapshot"])


class Migration(migrations.Migration):
    dependencies = [
        ("chat", "0009_chatreport_review_workflow"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatreport",
            name="evidence_snapshot",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.RunPython(
            backfill_chat_evidence,
            migrations.RunPython.noop,
        ),
    ]
