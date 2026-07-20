import json
from collections import Counter
from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from chat.models import ChatReport
from feed.models import Post, PostReport
from notifications.activity import (
    moderation_report_subject_user_id,
)
from notifications.models import Notification
from profiles.models import (
    ModerationAction,
    Profile,
    ProfileReport,
)


REPORT_SPECS = (
    (
        "profile_reports",
        ProfileReport,
        "profiles.profilereport",
    ),
    (
        "post_reports",
        PostReport,
        "feed.postreport",
    ),
    (
        "chat_reports",
        ChatReport,
        "chat.chatreport",
    ),
)


def report_metrics(
    model,
    related_object_type,
    *,
    active_staff_ids,
    stale_cutoff,
):
    queryset = model.objects.all()
    if model is PostReport:
        queryset = queryset.select_related("post")
    reports = list(queryset)
    status_counts = Counter(report.status for report in reports)
    pending = [
        report
        for report in reports
        if report.status == model.STATUS_PENDING
    ]
    pending_ids = [report.id for report in pending]

    alert_pairs = set(
        Notification.objects.filter(
            notification_type=Notification.TYPE_REPORT,
            related_object_type=related_object_type,
            related_object_id__in=pending_ids,
            recipient_id__in=active_staff_ids,
        ).values_list(
            "related_object_id",
            "recipient_id",
        )
    )
    alert_report_ids = {
        report_id for report_id, _recipient_id in alert_pairs
    }

    expected_alerts = 0
    missing_alerts = 0
    for report in pending:
        expected_recipients = {
            staff_id
            for staff_id in active_staff_ids
            if staff_id
            not in {
                report.reporter_id,
                (
                    moderation_report_subject_user_id(report)
                    if model is not ChatReport
                    else None
                ),
            }
        }
        expected_alerts += len(expected_recipients)
        missing_alerts += sum(
            (report.id, staff_id) not in alert_pairs
            for staff_id in expected_recipients
        )

    return {
        "total": len(reports),
        "pending": len(pending),
        "stale_pending": sum(
            report.created_at <= stale_cutoff
            for report in pending
        ),
        "reviewed": status_counts[model.STATUS_REVIEWED],
        "actioned": status_counts[model.STATUS_ACTIONED],
        "dismissed": status_counts[model.STATUS_DISMISSED],
        "expected_staff_alerts": expected_alerts,
        "missing_staff_alerts": missing_alerts,
        "pending_without_any_staff_alert": sum(
            report.id not in alert_report_ids
            for report in pending
        ),
    }


class Command(BaseCommand):
    help = (
        "Audit Heartly moderation queue age, staff-alert "
        "coverage, hidden content, and audit history."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--stale-hours",
            type=int,
            default=24,
            help=(
                "Pending reports at least this old are stale "
                "(default: 24)."
            ),
        )
        parser.add_argument(
            "--output",
            help="Optional JSON output path.",
        )
        parser.add_argument(
            "--fail-on-issues",
            action="store_true",
            help=(
                "Exit with an error when stale reports, missing "
                "staff alerts, or an unstaffed queue is found."
            ),
        )

    def handle(self, *args, **options):
        stale_hours = options["stale_hours"]
        if stale_hours < 1:
            raise CommandError("--stale-hours must be at least 1.")

        now = timezone.now()
        stale_cutoff = now - timedelta(hours=stale_hours)
        User = get_user_model()
        active_staff_ids = set(
            User.objects.filter(
                is_active=True,
                is_staff=True,
            ).values_list("id", flat=True)
        )

        queues = {
            name: report_metrics(
                model,
                related_object_type,
                active_staff_ids=active_staff_ids,
                stale_cutoff=stale_cutoff,
            )
            for name, model, related_object_type in REPORT_SPECS
        }

        total_pending = sum(
            metrics["pending"] for metrics in queues.values()
        )
        total_stale = sum(
            metrics["stale_pending"]
            for metrics in queues.values()
        )
        total_missing_alerts = sum(
            metrics["missing_staff_alerts"]
            for metrics in queues.values()
        )
        unstaffed_pending = (
            total_pending if not active_staff_ids else 0
        )
        has_issues = bool(
            total_stale
            or total_missing_alerts
            or unstaffed_pending
        )

        report = {
            "generated_at": now.isoformat(),
            "read_only": True,
            "stale_after_hours": stale_hours,
            "summary": {
                "active_staff": len(active_staff_ids),
                "total_pending_reports": total_pending,
                "total_stale_pending_reports": total_stale,
                "missing_staff_alerts": total_missing_alerts,
                "unstaffed_pending_reports": unstaffed_pending,
                "hidden_profiles": Profile.objects.filter(
                    hidden_by_moderation=True
                ).count(),
                "hidden_posts": Post.objects.filter(
                    hidden_by_moderation=True
                ).count(),
                "moderation_audit_rows": (
                    ModerationAction.objects.count()
                ),
                "has_issues": has_issues,
            },
            "queues": queues,
        }

        self.stdout.write("Heartly moderation queue audit")
        self.stdout.write("Read-only: no records changed")
        self.stdout.write(
            f"Stale threshold: {stale_hours} hour(s)"
        )
        self.stdout.write(
            f"Active staff: {len(active_staff_ids)}"
        )
        for name, metrics in queues.items():
            label = name.replace("_", " ").title()
            self.stdout.write(
                f"{label}: total={metrics['total']} "
                f"pending={metrics['pending']} "
                f"stale={metrics['stale_pending']} "
                f"missing_alerts={metrics['missing_staff_alerts']}"
            )
        self.stdout.write(f"Hidden profiles: {report['summary']['hidden_profiles']}")
        self.stdout.write(f"Hidden posts: {report['summary']['hidden_posts']}")
        self.stdout.write(
            "Moderation audit rows: "
            f"{report['summary']['moderation_audit_rows']}"
        )

        output = options.get("output")
        if output:
            output_path = Path(output)
            output_path.write_text(
                json.dumps(report, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            self.stdout.write(f"JSON report: {output_path}")

        if options["fail_on_issues"] and has_issues:
            raise CommandError(
                "Moderation queue issues detected."
            )
