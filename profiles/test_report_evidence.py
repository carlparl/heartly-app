from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from chat.models import ChatMessage, ChatReport, ChatThread
from feed.models import Post, PostReport

from .models import Profile, ProfileReport


User = get_user_model()


@override_settings(
    HEARTLY_ENFORCE_ADULT_IDENTITY=False,
    HEARTLY_REQUIRE_VERIFIED_EMAIL=False,
)
class ModerationEvidenceTests(TestCase):
    def setUp(self):
        self.reporter = User.objects.create_user(
            username="evidence_reporter",
            email="evidence-reporter@example.com",
            password="StrongPass123!",
        )
        self.target = User.objects.create_user(
            username="evidence_target",
            email="evidence-target@example.com",
            password="StrongPass123!",
        )
        profile = Profile.objects.get(user=self.target)
        profile.display_name = "Evidence Target"
        profile.bio = "Original profile marker"
        profile.save(update_fields=["display_name", "bio"])
        self.client.force_login(self.reporter)

    def test_profile_report_captures_bounded_snapshot(self):
        response = self.client.post(
            reverse(
                "profiles:report_profile",
                args=[self.target.id],
            ),
            {"reason": ProfileReport.REASON_SPAM},
        )
        self.assertEqual(response.status_code, 302)
        report = ProfileReport.objects.get(
            reporter=self.reporter,
            reported_user=self.target,
        )
        self.assertEqual(
            report.evidence_snapshot["schema_version"],
            1,
        )
        self.assertEqual(
            report.evidence_snapshot["bio"],
            "Original profile marker",
        )

    def test_post_report_snapshot_does_not_change_with_post(self):
        post = Post.objects.create(
            author=self.target,
            content="Original post marker",
        )
        response = self.client.post(
            reverse("feed:report_post", args=[post.id]),
            {"reason": PostReport.REASON_SPAM},
        )
        self.assertEqual(response.status_code, 302)
        report = PostReport.objects.get(post=post)
        post.content = "Changed after report"
        post.save(update_fields=["content"])
        report.refresh_from_db()
        self.assertEqual(
            report.evidence_snapshot["content"],
            "Original post marker",
        )

    def test_chat_report_captures_recent_message_snapshot(self):
        thread = ChatThread.get_or_create_between(
            self.reporter,
            self.target,
        )
        message = ChatMessage.objects.create(
            thread=thread,
            sender=self.target,
            text="Original chat marker",
        )
        response = self.client.post(
            reverse(
                "chat:report_thread_user",
                args=[thread.id],
            ),
            {"reason": ChatReport.REASON_SPAM},
        )
        self.assertEqual(response.status_code, 302)
        report = ChatReport.objects.get(thread=thread)
        message.text = "Changed after report"
        message.save(update_fields=["text"])
        report.refresh_from_db()
        self.assertEqual(
            report.evidence_snapshot["messages"][0]["text"],
            "Original chat marker",
        )
