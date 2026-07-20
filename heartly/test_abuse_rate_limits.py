from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from feed.models import Post


User = get_user_model()


TEST_REPORT_LIMITS = {
    "reports": {
        "limit": 1,
        "window": 60,
    },
}


@override_settings(
    HEARTLY_ENFORCE_ADULT_IDENTITY=False,
    HEARTLY_REQUIRE_VERIFIED_EMAIL=False,
    RATELIMIT_ENABLE=True,
    HEARTLY_RATE_LIMITS=TEST_REPORT_LIMITS,
    HEARTLY_TRUST_X_FORWARDED_FOR=False,
)
class AuthenticatedRateLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        self.reporter = User.objects.create_user(
            username="rate-reporter",
            email="rate-reporter@example.com",
            password="StrongPass123!",
        )
        self.author = User.objects.create_user(
            username="rate-author",
            email="rate-author@example.com",
            password="StrongPass123!",
        )
        self.posts = [
            Post.objects.create(
                author=self.author,
                content=f"Rate limit post {index}",
            )
            for index in range(2)
        ]
        self.client.force_login(self.reporter)

    def report(self, post):
        return self.client.post(
            reverse("feed:report_post", args=[post.id]),
            {"reason": "spam"},
            HTTP_ACCEPT="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def test_second_report_is_limited_with_retry_header(self):
        first = self.report(self.posts[0])
        second = self.report(self.posts[1])

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertFalse(second.json()["ok"])
        self.assertGreater(int(second["Retry-After"]), 0)
        self.assertIn("no-store", second["Cache-Control"])

    def test_authenticated_limit_is_isolated_per_user(self):
        self.report(self.posts[0])
        other = User.objects.create_user(
            username="other-reporter",
            email="other-reporter@example.com",
            password="StrongPass123!",
        )
        self.client.force_login(other)

        response = self.report(self.posts[1])

        self.assertEqual(response.status_code, 200)

    def test_staff_bypasses_member_write_limit(self):
        staff = User.objects.create_user(
            username="rate-staff",
            email="rate-staff@example.com",
            password="StrongPass123!",
            is_staff=True,
        )
        self.client.force_login(staff)

        first = self.report(self.posts[0])
        second = self.report(self.posts[1])

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)


@override_settings(
    RATELIMIT_ENABLE=True,
    HEARTLY_RATE_LIMITS={
        "auth_login": {
            "limit": 1,
            "window": 60,
        },
    },
    HEARTLY_TRUST_X_FORWARDED_FOR=False,
)
class AnonymousRateLimitTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_login_limit_is_keyed_without_account_enumeration(self):
        url = reverse("account_login")
        first = self.client.post(
            url,
            {
                "login": "unknown@example.com",
                "password": "not-the-password",
            },
        )
        second = self.client.post(
            url,
            {
                "login": "another@example.com",
                "password": "not-the-password",
            },
        )

        self.assertNotEqual(first.status_code, 429)
        self.assertEqual(second.status_code, 429)
        self.assertContains(
            second,
            "Please wait a moment",
            status_code=429,
        )
