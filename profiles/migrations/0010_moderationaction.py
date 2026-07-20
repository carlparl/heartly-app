from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("profiles", "0009_profilephoto"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ModerationAction",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("report_reviewed", "Report reviewed"),
                            ("report_actioned", "Report actioned"),
                            ("report_dismissed", "Report dismissed"),
                            ("profile_hidden", "Profile hidden"),
                            ("profile_restored", "Profile restored"),
                            ("post_hidden", "Post hidden"),
                            ("post_restored", "Post restored"),
                        ],
                        max_length=40,
                    ),
                ),
                (
                    "source_type",
                    models.CharField(
                        choices=[
                            ("profile", "Profile"),
                            ("profile_report", "Profile report"),
                            ("post", "Post"),
                            ("post_report", "Post report"),
                            ("chat_report", "Chat report"),
                        ],
                        max_length=40,
                    ),
                ),
                (
                    "source_object_id",
                    models.PositiveBigIntegerField(
                        blank=True,
                        null=True,
                    ),
                ),
                ("note", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "moderator",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="moderation_actions_performed",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "target_user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="moderation_actions_received",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
                "indexes": [
                    models.Index(
                        fields=["-created_at"],
                        name="profiles_mod_created_idx",
                    ),
                    models.Index(
                        fields=["target_user", "-created_at"],
                        name="profiles_mod_target_idx",
                    ),
                    models.Index(
                        fields=["action", "-created_at"],
                        name="profiles_mod_action_idx",
                    ),
                ],
            },
        ),
    ]
