import os
from django.db import migrations


ADMIN_EMAIL = "grahamwalz1@gmail.com"


def promote_existing_user(apps, schema_editor):
    User = apps.get_model("accounts", "CustomUser")

    password = os.environ.get("HEARTLY_ADMIN_PASSWORD", "").strip()

    user = User.objects.filter(email=ADMIN_EMAIL).first()

    if not user:
        user = User(email=ADMIN_EMAIL)

        username_field_exists = any(field.name == "username" for field in User._meta.fields)
        if username_field_exists:
            user.username = "grahamwalz1"

    user.is_staff = True
    user.is_superuser = True
    user.is_active = True

    if password:
        user.set_password(password)

    user.save()


def reverse_promote_existing_user(apps, schema_editor):
    # Do nothing on rollback. We do not want rollback to remove admin access accidentally.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_emailverificationcode"),
    ]

    operations = [
        migrations.RunPython(promote_existing_user, reverse_promote_existing_user),
    ]