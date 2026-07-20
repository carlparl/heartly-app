import json
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from feed.models import Post
from profiles.models import Profile, ProfileReport


User = get_user_model()


@override_settings(
    HEARTLY_ENFORCE_ADULT_IDENTITY=False,
    HEARTLY_REQUIRE_VERIFIED_EMAIL=False,
)
class AccountDataExportTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="export-owner",
            email="export-owner@example.com",
            password="StrongPass123!",
            date_of_birth=date(1990, 1, 1),
        )
        self.target = User.objects.create_user(
            username="export-target",
            email="private-target@example.com",
            password="StrongPass123!",
            date_of_birth=date(1991, 1, 1),
        )
        Profile.objects.get_or_create(user=self.user)
        Profile.objects.get_or_create(user=self.target)
        self.user.moderation_reason = "internal account safety reason"
        self.user.save(update_fields=["moderation_reason"])
        Post.objects.create(author=self.user, content="My exported post")
        ProfileReport.objects.create(
            reporter=self.user,
            reported_user=self.target,
            reason=ProfileReport.REASON_SPAM,
            details="My submitted report details",
            evidence_snapshot={"internal-only": "do not export"},
            moderator_note="private staff note",
        )

    def test_export_requires_authentication(self):
        response = self.client.get(reverse("data_export"))
        self.assertEqual(response.status_code, 302)

    def test_export_page_is_available_to_account_owner(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("data_export"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Type EXPORT")

    def test_restricted_account_can_still_access_privacy_export(self):
        self.user.moderation_status = User.MODERATION_BANNED
        self.user.save(update_fields=["moderation_status"])
        self.client.force_login(self.user)

        response = self.client.get(reverse("data_export"))

        self.assertEqual(response.status_code, 200)

    def test_export_requires_password_and_exact_confirmation(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("data_export"),
            {"password": "wrong", "confirm_export": "EXPORT"},
        )
        self.assertRedirects(response, reverse("data_export"))

        response = self.client.post(
            reverse("data_export"),
            {"password": "StrongPass123!", "confirm_export": "export"},
        )
        self.assertRedirects(response, reverse("data_export"))

    def test_export_contains_owned_data_and_excludes_internal_evidence(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("data_export"),
            {
                "password": "StrongPass123!",
                "confirm_export": "EXPORT",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn("no-store", response["Cache-Control"])
        report = json.loads(response.content)
        encoded = json.dumps(report)
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["account"]["email"], self.user.email)
        self.assertEqual(
            report["collections"]["posts"]["records"][0]["content"],
            "My exported post",
        )
        self.assertIn("My submitted report details", encoded)
        self.assertNotIn("internal-only", encoded)
        self.assertNotIn("private staff note", encoded)
        self.assertNotIn("internal account safety reason", encoded)
        self.assertNotIn("private-target@example.com", encoded)

    @override_settings(HEARTLY_DATA_EXPORT_MAX_RECORDS=1)
    def test_export_marks_truncated_collections(self):
        Post.objects.create(author=self.user, content="Second post")
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("data_export"),
            {
                "password": "StrongPass123!",
                "confirm_export": "EXPORT",
            },
        )
        report = json.loads(response.content)
        self.assertTrue(report["collections"]["posts"]["truncated"])
        self.assertEqual(
            len(report["collections"]["posts"]["records"]),
            1,
        )
