from django.contrib.auth import get_user_model
from django.test import TestCase

from chat.models import ChatMessage, ChatReport, ChatThread
from feed.models import Comment, Post
from matches.models import MutualMatch
from notifications.activity import (
    mark_thread_message_notifications_read,
    notify_chat_message,
    notify_chat_report,
    notify_mutual_match,
    notify_post_comment,
    notify_post_like,
    notify_profile_like,
)
from notifications.models import Notification


class NotificationActivityTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="owner", email="owner@example.com", password="Pass12345!")
        self.actor = User.objects.create_user(username="actor", email="actor@example.com", password="Pass12345!")
        self.third = User.objects.create_user(username="third", email="third@example.com", password="Pass12345!")
        self.staff = User.objects.create_user(username="moderator", email="moderator@example.com", password="Pass12345!", is_staff=True)

    def test_post_like_is_deduplicated_and_removed_on_unlike(self):
        post = Post.objects.create(author=self.owner, content="Test")
        notify_post_like(post, self.actor, True)
        notify_post_like(post, self.actor, True)
        qs = Notification.objects.filter(recipient=self.owner, actor=self.actor, related_object_type="feed.post", related_object_id=post.id)
        self.assertEqual(qs.count(), 1)
        notify_post_like(post, self.actor, False)
        self.assertFalse(qs.exists())

    def test_comment_and_reply_notify_relevant_people(self):
        post = Post.objects.create(author=self.owner, content="Test")
        parent = Comment.objects.create(post=post, user=self.actor, content="Comment")
        notify_post_comment(parent)
        reply = Comment.objects.create(post=post, user=self.third, parent=parent, content="Reply")
        notify_post_comment(reply)
        self.assertTrue(Notification.objects.filter(recipient=self.owner, related_object_type="feed.comment", related_object_id=parent.id).exists())
        self.assertTrue(Notification.objects.filter(recipient=self.actor, related_object_type="feed.comment_reply", related_object_id=reply.id).exists())
        self.assertTrue(Notification.objects.filter(recipient=self.owner, related_object_type="feed.comment_reply", related_object_id=reply.id).exists())

    def test_profile_like_becomes_match_notifications(self):
        notify_profile_like(self.actor, self.owner, active=True)
        self.assertTrue(Notification.objects.filter(related_object_type="matches.profile_like").exists())
        match = MutualMatch.create_safe(self.owner, self.actor)
        notify_mutual_match(match, self.owner, self.actor)
        self.assertFalse(Notification.objects.filter(related_object_type="matches.profile_like").exists())
        self.assertEqual(Notification.objects.filter(notification_type=Notification.TYPE_MATCH, related_object_id=match.id).count(), 2)

    def test_opening_thread_marks_message_notification_read(self):
        thread = ChatThread.get_or_create_between(self.owner, self.actor)
        message = ChatMessage.objects.create(thread=thread, sender=self.actor, text="Hello")
        notification = notify_chat_message(message)
        self.assertFalse(notification.is_read)
        self.assertEqual(mark_thread_message_notifications_read(thread, self.owner), 1)
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    def test_chat_report_notifies_staff_once(self):
        thread = ChatThread.get_or_create_between(self.owner, self.actor)
        report = ChatReport.objects.create(thread=thread, reporter=self.owner, reported_user=self.actor, reason=ChatReport.REASON_SPAM, details="Test")
        notify_chat_report(report)
        notify_chat_report(report)
        self.assertEqual(Notification.objects.filter(recipient=self.staff, related_object_type="chat.chatreport", related_object_id=report.id).count(), 1)
