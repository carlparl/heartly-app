from django.core.management.base import BaseCommand

from feed.models import Story


class Command(BaseCommand):
    help = "Delete expired Heartly Stories and their viewer receipts."

    def handle(self, *args, **options):
        deleted_total, deleted_by_model = Story.objects.expired().delete()
        story_count = deleted_by_model.get("feed.Story", 0)

        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {story_count} expired "
                f"{'Story' if story_count == 1 else 'Stories'} "
                f"({deleted_total} database rows including viewer receipts)."
            )
        )
