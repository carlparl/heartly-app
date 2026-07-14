# Generated for Heartly five-hour Stories on 2026-07-14

import cloudinary_storage.storage
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("feed", "0008_postsave"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Story",
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
                ("caption", models.CharField(blank=True, max_length=280)),
                (
                    "image",
                    models.ImageField(
                        blank=True,
                        null=True,
                        upload_to="stories/images/",
                    ),
                ),
                (
                    "video",
                    models.FileField(
                        blank=True,
                        null=True,
                        storage=cloudinary_storage.storage.VideoMediaCloudinaryStorage(),
                        upload_to="stories/videos/",
                    ),
                ),
                ("created_at", models.DateTimeField(editable=False)),
                (
                    "expires_at",
                    models.DateTimeField(db_index=True, editable=False),
                ),
                (
                    "author",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="stories",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["author", "expires_at"],
                        name="feed_story_author_exp_idx",
                    ),
                    models.Index(
                        fields=["expires_at", "created_at"],
                        name="feed_story_exp_created_idx",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="StoryView",
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
                ("viewed_at", models.DateTimeField(auto_now_add=True)),
                (
                    "story",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="views",
                        to="feed.story",
                    ),
                ),
                (
                    "viewer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="story_views",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-viewed_at"],
                "indexes": [
                    models.Index(
                        fields=["story", "viewed_at"],
                        name="feed_storyv_story_view_idx",
                    ),
                    models.Index(
                        fields=["viewer", "viewed_at"],
                        name="feed_storyv_user_view_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("story", "viewer"),
                        name="unique_story_view_per_user",
                    ),
                ],
            },
        ),
    ]
