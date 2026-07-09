import os

from django.contrib.auth.hashers import make_password
from django.db import migrations


ADMIN_EMAIL = "grahamwalz1@gmail.com"
ADMIN_USERNAME = "grahamwalz1"


def promote_existing_user(apps, schema_editor):
    User = apps.get_model("accounts", "CustomUser")

    password = os.environ.get("HEARTLY_ADMIN_PASSWORD", "").strip()

    user = User.objects.filter(email=ADMIN_EMAIL).first()

    if not user:
        user = User(email=ADMIN_EMAIL)

        field_names = {field.name for field in User._meta.fields}

        if "username" in field_names:
            user.username = ADMIN_USERNAME

    user.is_staff = True
    user.is_superuser = True
    user.is_active = True

    if password:
        user.password = make_password(password)

    user.save()


def reverse_promote_existing_user(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_emailverificationcode"),
    ]

    operations = [
        migrations.RunPython(promote_existing_user, reverse_promote_existing_user),
    ]


