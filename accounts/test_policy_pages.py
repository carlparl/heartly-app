from django.test import TestCase
from django.urls import reverse


class PublicPolicyPageTests(TestCase):
    def test_public_policy_pages_are_available(self):
        expected = {
            "community_guidelines": "Community Guidelines",
            "privacy_policy": "Privacy Policy",
            "terms_of_service": "Terms of Service",
        }
        for route_name, heading in expected.items():
            with self.subTest(route=route_name):
                response = self.client.get(reverse(route_name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, heading)
