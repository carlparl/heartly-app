import django.db.models.deletion
from django.db import migrations, models


def copy_legacy_profile_pictures(apps, schema_editor):
    Profile = apps.get_model("profiles", "Profile")
    ProfilePhoto = apps.get_model("profiles", "ProfilePhoto")

    profiles = (
        Profile.objects.exclude(profile_picture__isnull=True)
        .exclude(profile_picture="")
        .only("id", "profile_picture")
    )

    for profile in profiles.iterator():
        image_name = str(profile.profile_picture or "").strip()
        if not image_name:
            continue

        ProfilePhoto.objects.get_or_create(
            profile_id=profile.id,
            position=1,
            defaults={"image": image_name},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("profiles", "0008_profile_connection_goal"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProfilePhoto",
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
                ("image", models.ImageField(upload_to="profiles/photos/")),
                ("position", models.PositiveSmallIntegerField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "profile",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="photos",
                        to="profiles.profile",
                    ),
                ),
            ],
            options={"ordering": ["position", "id"]},
        ),
        migrations.AddConstraint(
            model_name="profilephoto",
            constraint=models.UniqueConstraint(
                fields=("profile", "position"),
                name="unique_profile_photo_position",
            ),
        ),
        migrations.AddConstraint(
            model_name="profilephoto",
            constraint=models.CheckConstraint(
                condition=models.Q(position__gte=1, position__lte=4),
                name="profile_photo_position_1_to_4",
            ),
        ),
        migrations.RunPython(
            copy_legacy_profile_pictures,
            migrations.RunPython.noop,
        ),
    ]
