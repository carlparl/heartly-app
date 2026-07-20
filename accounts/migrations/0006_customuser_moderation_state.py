from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_promote_existing_admin"),
    ]

    operations = [
        migrations.AddField(
            model_name="customuser",
            name="moderation_expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="customuser",
            name="moderation_reason",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="customuser",
            name="moderation_status",
            field=models.CharField(
                choices=[
                    ("clear", "No account restriction"),
                    ("suspended", "Suspended"),
                    ("banned", "Banned"),
                ],
                db_index=True,
                default="clear",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="customuser",
            name="moderation_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="customuser",
            name="moderation_updated_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="+",
                to="accounts.customuser",
            ),
        ),
    ]
