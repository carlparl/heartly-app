from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from profiles.models import Profile, UserBlock

from .models import Comment, Post, PostLike, PostReport


User = get_user_model()


@override_settings(
    HEARTLY_ENFORCE_ADULT_IDENTITY=False,
    HEARTLY_REQUIRE_VERIFIED_EMAIL=False,
    PASSWORD_HASHERS=[
        "django.contrib.auth.hashers.MD5PasswordHasher"
    ],
)
class FeedModerationHardeningTests(TestCase):
    def create_user(self, username):
        user = User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="StrongPass123!",
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
        self.viewer = self.create_user("feed_viewer")
        self.visible_author = self.create_user("visible_author")
        self.blocked_author = self.create_user("blocked_author")
        self.moderated_author = self.create_user(
            "moderated_author"
        )
        self.moderated_author.profile.hidden_by_moderation = True
        self.moderated_author.profile.save(
            update_fields=[
                "hidden_by_moderation",
                "updated_at",
            ]
        )
        UserBlock.objects.create(
            blocker=self.viewer,
            blocked=self.blocked_author,
        )
        self.client.force_login(self.viewer)

    def test_feed_hides_blocked_and_moderated_authors(self):
        Post.objects.create(
            author=self.visible_author,
            content="Visible post marker",
        )
        Post.objects.create(
            author=self.blocked_author,
            content="Blocked post marker",
        )
        Post.objects.create(
            author=self.moderated_author,
            content="Moderated post marker",
        )

        response = self.client.get(reverse("feed:feed_home"))

        self.assertContains(response, "Visible post marker")
        self.assertNotContains(response, "Blocked post marker")
        self.assertNotContains(response, "Moderated post marker")

    def test_feed_hides_comments_from_blocked_members(self):
        post = Post.objects.create(
            author=self.visible_author,
            content="Comment visibility post",
        )
        Comment.objects.create(
            post=post,
            user=self.visible_author,
            content="Visible comment marker",
        )
        Comment.objects.create(
            post=post,
            user=self.blocked_author,
            content="Blocked comment marker",
        )

        response = self.client.get(reverse("feed:feed_home"))

        self.assertContains(response, "Visible comment marker")
        self.assertNotContains(response, "Blocked comment marker")

    def test_blocked_post_cannot_be_liked_by_direct_url(self):
        post = Post.objects.create(
            author=self.blocked_author,
            content="Unavailable post",
        )

        response = self.client.post(
            reverse("feed:like_post", args=[post.id]),
            {"reaction_type": "love"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(
            PostLike.objects.filter(
                post=post,
                user=self.viewer,
            ).exists()
        )

    def test_post_report_is_saved_once(self):
        post = Post.objects.create(
            author=self.visible_author,
            content="Report persistence post",
        )
        url = reverse("feed:report_post", args=[post.id])
        headers = {
            "HTTP_X_REQUESTED_WITH": "XMLHttpRequest",
            "HTTP_ACCEPT": "application/json",
        }

        first = self.client.post(
            url,
            {
                "reason": PostReport.REASON_SPAM,
                "details": "Repeated content",
            },
            **headers,
        )
        second = self.client.post(url, {}, **headers)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(first.json()["created"])
        self.assertFalse(second.json()["created"])
        self.assertEqual(
            PostReport.objects.filter(
                post=post,
                reporter=self.viewer,
            ).count(),
            1,
        )
