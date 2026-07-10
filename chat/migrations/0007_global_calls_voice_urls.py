from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("chat", "0006_chatmessage_reply_to_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="chatattachment",
            name="file",
            field=models.FileField(blank=True, null=True, upload_to="chat_attachments/%Y/%m/"),
        ),
        migrations.AddField(
            model_name="chatattachment",
            name="external_url",
            field=models.URLField(blank=True, max_length=1000),
        ),
        migrations.AddField(
            model_name="chatattachment",
            name="cloudinary_public_id",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="chatattachment",
            name="content_type",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="chatattachment",
            name="duration_seconds",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
