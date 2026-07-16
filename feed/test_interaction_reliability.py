from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from feed.models import (
    Comment,
    CommentReaction,
    Post,
    PostLike,
    PostSave,
)


User = get_user_model()


@override_settings(
    PASSWORD_HASHERS=[
        "django.contrib.auth.hashers.MD5PasswordHasher"
    ]
)
class FeedInteractionReliabilityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="feedactor",
            email="feedactor@example.com",
            password="Pass12345!",
        )
        self.author = User.objects.create_user(
            username="feedauthor",
            email="feedauthor@example.com",
            password="Pass12345!",
        )
        self.post = Post.objects.create(
            author=self.author,
            content="Reliable feed post",
        )
        self.client.force_login(self.user)

    def ajax_post(self, url, data=None):
        return self.client.post(
            url,
            data or {},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )

    def test_post_like_returns_targeted_json(self):
        response = self.ajax_post(
            reverse(
                "feed:react_post",
                args=[self.post.id],
            ),
            {"reaction_type": "love"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["reacted"])
        self.assertEqual(payload["likes_count"], 1)
        self.assertNotIn("post_html", payload)
        self.assertTrue(
            PostLike.objects.filter(
                post=self.post,
                user=self.user,
            ).exists()
        )

    def test_second_like_click_removes_reaction(self):
        PostLike.objects.create(
            post=self.post,
            user=self.user,
            reaction_type="love",
        )

        response = self.ajax_post(
            reverse(
                "feed:react_post",
                args=[self.post.id],
            ),
            {"reaction_type": "love"},
        )

        payload = response.json()
        self.assertFalse(payload["reacted"])
        self.assertEqual(payload["likes_count"], 0)
        self.assertFalse(
            PostLike.objects.filter(
                post=self.post,
                user=self.user,
            ).exists()
        )

    def test_save_toggle_returns_targeted_json(self):
        url = reverse(
            "feed:save_post",
            args=[self.post.id],
        )

        first = self.ajax_post(url)
        self.assertTrue(first.json()["saved"])
        self.assertNotIn("post_html", first.json())

        second = self.ajax_post(url)
        self.assertFalse(second.json()["saved"])
        self.assertFalse(
            PostSave.objects.filter(
                post=self.post,
                user=self.user,
            ).exists()
        )

    def test_comment_returns_only_new_comment_html(self):
        response = self.ajax_post(
            reverse(
                "feed:comment_post",
                args=[self.post.id],
            ),
            {"content": "Targeted comment"},
        )

        payload = response.json()
        self.assertEqual(payload["comments_count"], 1)
        self.assertIn(
            "Targeted comment",
            payload["comment_html"],
        )
        self.assertNotIn("post_html", payload)

    def test_reply_stays_attached_to_parent(self):
        parent = Comment.objects.create(
            post=self.post,
            user=self.author,
            content="Parent comment",
        )

        response = self.ajax_post(
            reverse(
                "feed:reply_comment",
                args=[parent.id],
            ),
            {"content": "Attached reply"},
        )

        payload = response.json()
        self.assertEqual(payload["parent_id"], parent.id)
        self.assertEqual(payload["comments_count"], 1)
        self.assertEqual(payload["replies_count"], 1)
        self.assertIn(
            "Attached reply",
            payload["reply_html"],
        )

        reply = Comment.objects.get(
            id=payload["reply_id"]
        )
        self.assertEqual(reply.parent_id, parent.id)

    def test_comment_reaction_returns_exact_count(self):
        comment = Comment.objects.create(
            post=self.post,
            user=self.author,
            content="React here",
        )

        response = self.ajax_post(
            reverse(
                "feed:react_comment",
                args=[comment.id],
            ),
            {"reaction_type": "love"},
        )

        payload = response.json()
        self.assertTrue(payload["reacted"])
        self.assertEqual(payload["reaction_count"], 1)
        self.assertNotIn("post_html", payload)
        self.assertTrue(
            CommentReaction.objects.filter(
                comment=comment,
                user=self.user,
            ).exists()
        )

    def test_comment_template_hides_timestamp(self):
        source = (
            Path(settings.BASE_DIR)
            / "templates/feed/_comment_item.html"
        ).read_text(encoding="utf-8")

        self.assertNotIn(
            "comment.created_at|timesince",
            source,
        )

    def test_feed_javascript_has_optimistic_rollback(self):
        source = (
            Path(settings.BASE_DIR)
            / "static/js/heartly-feed-ajax.js"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "applyOptimisticState",
            source,
        )
        self.assertIn(
            "rollbackOptimisticState",
            source,
        )
        self.assertIn(
            "insertCommentResponse",
            source,
        )
        self.assertIn(
            "insertReplyResponse",
            source,
        )
