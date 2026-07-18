from django.db import migrations, models


def migrate_legacy_friendship_goals(apps, schema_editor):
    Profile = apps.get_model("profiles", "Profile")

    Profile.objects.filter(
        user__interested_in="friends",
    ).update(
        connection_goal="friendship",
    )


def reverse_legacy_friendship_goals(apps, schema_editor):
    Profile = apps.get_model("profiles", "Profile")

    Profile.objects.filter(
        user__interested_in="friends",
        connection_goal="friendship",
    ).update(
        connection_goal="dating",
    )


class Migration(migrations.Migration):

    dependencies = [
        ("profiles", "0007_delete_photo"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="connection_goal",
            field=models.CharField(
                choices=[
                    ("dating", "Dating"),
                    ("friendship", "Friendship"),
                    ("both", "Dating and friendship"),
                ],
                default="dating",
                max_length=20,
            ),
        ),
        migrations.RunPython(
            migrate_legacy_friendship_goals,
            reverse_legacy_friendship_goals,
        ),
    ]
