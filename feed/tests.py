from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Comment, Post, PostLike


User = get_user_model()


@override_settings(
    PASSWORD_HASHERS=[
        "django.contrib.auth.hashers.MD5PasswordHasher"
    ]
)
class FeedRoutesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="feeduser",
            email="feeduser@example.com",
            password="StrongPass123!",
        )
        self.client.force_login(self.user)

    def test_feed_home_loads(self):
        response = self.client.get(
            reverse("feed:feed_home")
        )
        self.assertEqual(response.status_code, 200)

    def test_create_post_works(self):
        response = self.client.post(
            reverse("feed:create_post"),
            {"content": "Testing a post."},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Post.objects.filter(
                author=self.user,
                content="Testing a post.",
            ).exists()
        )

    def test_like_post_works(self):
        post = Post.objects.create(
            author=self.user,
            content="Like test.",
        )

        response = self.client.post(
            reverse(
                "feed:react_post",
                args=[post.id],
            ),
            {"reaction_type": "love"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            PostLike.objects.filter(
                post=post,
                user=self.user,
            ).exists()
        )

    def test_comment_post_works(self):
        post = Post.objects.create(
            author=self.user,
            content="Comment test.",
        )

        response = self.client.post(
            reverse(
                "feed:comment_post",
                args=[post.id],
            ),
            {"content": "Nice post."},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Comment.objects.filter(
                post=post,
                user=self.user,
                content="Nice post.",
            ).exists()
        )

    def test_edit_post_works(self):
        post = Post.objects.create(
            author=self.user,
            content="Old content.",
        )

        response = self.client.post(
            reverse(
                "feed:edit_post",
                args=[post.id],
            ),
            {"content": "Updated content."},
        )

        self.assertEqual(response.status_code, 302)

        post.refresh_from_db()
        self.assertEqual(
            post.content,
            "Updated content.",
        )

    def test_delete_post_works(self):
        post = Post.objects.create(
            author=self.user,
            content="Delete me.",
        )

        response = self.client.post(
            reverse(
                "feed:delete_post",
                args=[post.id],
            )
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            Post.objects.filter(
                id=post.id
            ).exists()
        )
