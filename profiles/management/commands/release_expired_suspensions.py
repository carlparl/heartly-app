from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from profiles.models import ModerationAction


class Command(BaseCommand):
    help = (
        "Dry-run or release expired Heartly account suspensions. "
        "Profile visibility is never changed automatically."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply releases. Without this flag the command is read-only.",
        )

    def handle(self, *args, **options):
        User = get_user_model()
        now = timezone.now()
        queryset = User.objects.filter(
            is_staff=False,
            is_superuser=False,
            moderation_status=User.MODERATION_SUSPENDED,
            moderation_expires_at__isnull=False,
            moderation_expires_at__lte=now,
        ).order_by("id")
        user_ids = list(queryset.values_list("id", flat=True))
        applied = 0

        if options["apply"] and user_ids:
            with transaction.atomic():
                users = list(
                    User.objects.select_for_update().filter(
                        id__in=user_ids,
                        moderation_status=(
                            User.MODERATION_SUSPENDED
                        ),
                        moderation_expires_at__lte=now,
                    )
                )
                User.objects.filter(
                    id__in=[user.id for user in users]
                ).update(
                    moderation_status=User.MODERATION_CLEAR,
                    moderation_reason="",
                    moderation_expires_at=None,
                    moderation_updated_at=now,
                    moderation_updated_by=None,
                )
                ModerationAction.objects.bulk_create(
                    [
                        ModerationAction(
                            moderator=None,
                            target_user=user,
                            action=(
                                ModerationAction
                                .ACTION_ACCOUNT_RESTORED
                            ),
                            source_type=(
                                ModerationAction.SOURCE_ACCOUNT
                            ),
                            source_object_id=user.id,
                            note=(
                                "Expired suspension released by "
                                "scheduled maintenance."
                            ),
                        )
                        for user in users
                    ]
                )
                applied = len(users)

        self.stdout.write("Heartly expired suspension release")
        self.stdout.write(
            "Mode: APPLY"
            if options["apply"]
            else "Mode: DRY RUN (no database changes)"
        )
        self.stdout.write(f"Expired suspensions: {len(user_ids)}")
        self.stdout.write(f"Released accounts: {applied}")
        self.stdout.write(
            "Profile visibility changes: 0"
        )
