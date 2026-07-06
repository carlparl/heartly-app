from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse

from .models import HeartlyMessage


User = get_user_model()


class AIFeaturesRoutesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="aiuser",
            email="aiuser@example.com",
            password="StrongPass123!"
        )
        self.client.login(username="aiuser", password="StrongPass123!")

    def test_ai_coach_page_loads(self):
        response = self.client.get(reverse("ai_features:ai_coach"))
        self.assertEqual(response.status_code, 200)

    def test_ai_coach_message_creates_user_and_coach_message(self):
        response = self.client.post(reverse("ai_features:ai_coach"), {
            "message": "I need dating advice"
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(HeartlyMessage.objects.filter(user=self.user).count(), 2)

        user_message = HeartlyMessage.objects.filter(user=self.user, role="user").first()
        coach_message = HeartlyMessage.objects.filter(user=self.user, role="coach").first()

        self.assertIsNotNone(user_message)
        self.assertIsNotNone(coach_message)

    def test_ai_coach_reset_clears_messages(self):
        HeartlyMessage.objects.create(
            user=self.user,
            role="user",
            text="Hello"
        )

        response = self.client.post(reverse("ai_features:ai_coach"), {
            "action": "reset"
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(HeartlyMessage.objects.filter(user=self.user).count(), 0)