from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("chat", "0007_global_calls_voice_urls"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatmessage",
            name="client_message_id",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                max_length=64,
            ),
        ),
        migrations.AddConstraint(
            model_name="chatmessage",
            constraint=models.UniqueConstraint(
                condition=~models.Q(client_message_id=""),
                fields=(
                    "thread",
                    "sender",
                    "client_message_id",
                ),
                name="uniq_chat_client_message",
            ),
        ),
    ]
