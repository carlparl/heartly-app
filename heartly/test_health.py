from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.urls import reverse


class LivenessTests(SimpleTestCase):
    def test_liveness_is_public_and_minimal(self):
        response = self.client.get(reverse("health_liveness"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"service": "heartly", "status": "ok"},
        )
        self.assertEqual(
            response["X-Robots-Tag"],
            "noindex, nofollow",
        )
        self.assertIn("X-Request-ID", response)

    def test_safe_incoming_request_id_is_preserved(self):
        response = self.client.get(
            reverse("health_liveness"),
            HTTP_X_REQUEST_ID="render-check-1234",
        )

        self.assertEqual(
            response["X-Request-ID"],
            "render-check-1234",
        )

    def test_unsafe_request_id_is_replaced(self):
        response = self.client.get(
            reverse("health_liveness"),
            HTTP_X_REQUEST_ID="bad\nlog-value",
        )

        self.assertNotEqual(
            response["X-Request-ID"],
            "bad\nlog-value",
        )
        self.assertEqual(len(response["X-Request-ID"]), 32)


class ReadinessTests(TestCase):
    def test_readiness_checks_database_and_cache(self):
        response = self.client.get(reverse("health_readiness"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ready")

    @patch("heartly.health.cache.get", return_value=None)
    def test_readiness_failure_is_generic(self, cache_get):
        response = self.client.get(reverse("health_readiness"))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {"service": "heartly", "status": "unavailable"},
        )
        self.assertNotIn("database", response.content.decode())
        self.assertNotIn("cache", response.content.decode())
