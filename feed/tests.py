from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse

from .models import Post, PostLike, Comment


User = get_user_model()


class FeedRoutesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="feeduser",
            email="feeduser@example.com",
            password="StrongPass123!"
        )
        self.client.login(username="feeduser", password="StrongPass123!")

    def test_feed_home_loads(self):
        response = self.client.get(reverse("feed_home"))
        self.assertEqual(response.status_code, 200)

    def test_create_post_works(self):
        response = self.client.post(reverse("create_post"), {
            "content": "Testing a post."
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Post.objects.filter(content="Testing a post.").exists())

    def test_like_post_works(self):
        post = Post.objects.create(user=self.user, content="Like test.")

        response = self.client.post(reverse("like_post", args=[post.id]))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(PostLike.objects.filter(post=post, user=self.user).exists())

    def test_comment_post_works(self):
        post = Post.objects.create(user=self.user, content="Comment test.")

        response = self.client.post(reverse("add_comment", args=[post.id]), {
            "content": "Nice post."
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Comment.objects.filter(post=post, content="Nice post.").exists())

    def test_edit_post_works(self):
        post = Post.objects.create(user=self.user, content="Old content.")

        response = self.client.post(reverse("edit_post", args=[post.id]), {
            "content": "Updated content."
        })

        self.assertEqual(response.status_code, 302)

        post.refresh_from_db()
        self.assertEqual(post.content, "Updated content.")

    def test_delete_post_works(self):
        post = Post.objects.create(user=self.user, content="Delete me.")

        response = self.client.post(reverse("delete_post", args=[post.id]))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Post.objects.filter(id=post.id).exists())