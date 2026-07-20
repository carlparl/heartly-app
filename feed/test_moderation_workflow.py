from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from notifications.models import Notification
from profiles.models import ModerationAction, Profile

from .admin import PostAdmin, PostReportAdmin
from .models import Post, PostLike, PostReport


User = get_user_model()


@override_settings(
    HEARTLY_ENFORCE_ADULT_IDENTITY=False,
    HEARTLY_REQUIRE_VERIFIED_EMAIL=False,
    PASSWORD_HASHERS=[
        "django.contrib.auth.hashers.MD5PasswordHasher"
    ],
)
class FeedModerationWorkflowTests(TestCase):
    def create_user(self, username, **extra):
        user = User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="StrongPass123!",
            **extra,
        )
        profile = Profile.objects.get(user=user)
        profile.profile_visible = True
        profile.hidden_by_moderation = False
        profile.save(
            update_fields=[
                "profile_visible",
                "hidden_by_moderation",
                "updated_at",
            ]
        )
        return user

    def setUp(self):
        self.moderator = self.create_user(
            "feed_moderator",
            is_staff=True,
            is_superuser=True,
        )
        self.viewer = self.create_user("feed_workflow_viewer")
        self.author = self.create_user("feed_workflow_author")
        self.post = Post.objects.create(
            author=self.author,
            content="Moderation workflow marker",
        )
        self.request = RequestFactory().post("/admin/")
        self.request.user = self.moderator
        self.client.force_login(self.viewer)

    def test_post_hide_is_reversible_audited_and_resolves_alerts(self):
        notification = Notification.objects.create(
            recipient=self.viewer,
            actor=self.author,
            notification_type=Notification.TYPE_LIKE,
            title="Post alert",
            related_object_type="feed.post",
            related_object_id=self.post.id,
        )
        model_admin = PostAdmin(Post, admin.site)
        queryset = Post.objects.filter(pk=self.post.pk)

        model_admin.hide_posts(self.request, queryset)
        self.post.refresh_from_db()
        notification.refresh_from_db()

        self.assertTrue(self.post.hidden_by_moderation)
        self.assertEqual(self.post.moderated_by, self.moderator)
        self.assertIsNotNone(self.post.moderated_at)
        self.assertTrue(notification.is_resolved)
        self.assertNotContains(
            self.client.get(reverse("feed:feed_home")),
            "Moderation workflow marker",
        )
        self.assertTrue(
            ModerationAction.objects.filter(
                action=ModerationAction.ACTION_POST_HIDDEN,
                source_type=ModerationAction.SOURCE_POST,
                source_object_id=self.post.id,
            ).exists()
        )

        model_admin.restore_posts(self.request, queryset)
        self.post.refresh_from_db()
        self.assertFalse(self.post.hidden_by_moderation)
        self.assertContains(
            self.client.get(reverse("feed:feed_home")),
            "Moderation workflow marker",
        )

    def test_post_report_dismissal_is_audited(self):
        report = PostReport.objects.create(
            post=self.post,
            reporter=self.viewer,
            reason=PostReport.REASON_SPAM,
            moderator_note="Report did not meet the action threshold.",
        )
        model_admin = PostReportAdmin(
            PostReport,
            admin.site,
        )

        model_admin.mark_dismissed(
            self.request,
            PostReport.objects.filter(pk=report.pk),
        )

        report.refresh_from_db()
        self.assertTrue(report.reviewed)
        self.assertEqual(
            report.status,
            PostReport.STATUS_DISMISSED,
        )
        self.assertEqual(report.reviewed_by, self.moderator)
        self.assertTrue(
            ModerationAction.objects.filter(
                action=(
                    ModerationAction.ACTION_REPORT_DISMISSED
                ),
                source_type=(
                    ModerationAction.SOURCE_POST_REPORT
                ),
                source_object_id=report.id,
            ).exists()
        )

    def test_report_action_hides_post_from_direct_interaction(self):
        report = PostReport.objects.create(
            post=self.post,
            reporter=self.viewer,
            reason=PostReport.REASON_INAPPROPRIATE,
        )
        model_admin = PostReportAdmin(
            PostReport,
            admin.site,
        )

        model_admin.hide_reported_posts(
            self.request,
            PostReport.objects.filter(pk=report.pk),
        )

        report.refresh_from_db()
        self.post.refresh_from_db()
        self.assertEqual(
            report.status,
            PostReport.STATUS_ACTIONED,
        )
        self.assertTrue(self.post.hidden_by_moderation)
        response = self.client.post(
            reverse("feed:like_post", args=[self.post.id]),
            {"reaction_type": "love"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(
            PostLike.objects.filter(
                post=self.post,
                user=self.viewer,
            ).exists()
        )
