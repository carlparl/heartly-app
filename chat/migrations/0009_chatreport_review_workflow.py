from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("chat", "0008_chatmessage_client_message_id"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="chatreport",
            name="moderator_note",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="chatreport",
            name="reviewed",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="chatreport",
            name="reviewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="chatreport",
            name="reviewed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="reviewed_chat_reports",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="chatreport",
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
    ]
