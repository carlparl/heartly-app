from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from feed.models import Comment, Post

from .models import BlockedUser, Report


User = get_user_model()


@login_required
@require_POST
def block_user(request, user_id):
    blocked_user = get_object_or_404(User, id=user_id)

    if blocked_user == request.user:
        messages.error(request, "You cannot block yourself.")
        return redirect("feed:feed_home")

    BlockedUser.objects.get_or_create(
        blocker=request.user,
        blocked=blocked_user,
        defaults={
            "reason": request.POST.get("reason", "").strip(),
        },
    )

    messages.success(request, f"@{blocked_user.username} has been blocked.")
    return redirect("feed:feed_home")


@login_required
@require_POST
def unblock_user(request, user_id):
    blocked_user = get_object_or_404(User, id=user_id)

    BlockedUser.objects.filter(
        blocker=request.user,
        blocked=blocked_user,
    ).delete()

    messages.success(request, f"@{blocked_user.username} has been unblocked.")
    return redirect("blocked_users")


@login_required
@require_POST
def report_user(request, user_id):
    reported_user = get_object_or_404(User, id=user_id)

    if reported_user == request.user:
        messages.error(request, "You cannot report yourself.")
        return redirect("feed:feed_home")

    Report.objects.create(
        reporter=request.user,
        target_type=Report.TARGET_USER,
        reported_user=reported_user,
        reason=request.POST.get("reason", Report.REASON_OTHER),
        details=request.POST.get("details", "").strip(),
    )

    messages.success(request, "User report submitted. Our team will review it.")
    return redirect("feed:feed_home")


@login_required
@require_POST
def report_post(request, post_id):
    post = get_object_or_404(Post, id=post_id)

    if post.user == request.user:
        messages.error(request, "You cannot report your own post.")
        return redirect("feed:feed_home")

    Report.objects.create(
        reporter=request.user,
        target_type=Report.TARGET_POST,
        reported_user=post.user,
        post=post,
        reason=request.POST.get("reason", Report.REASON_INAPPROPRIATE),
        details=request.POST.get("details", "").strip(),
    )

    messages.success(request, "Post report submitted. Our team will review it.")
    return redirect("feed:feed_home")


@login_required
@require_POST
def report_comment(request, comment_id):
    comment = get_object_or_404(Comment, id=comment_id)

    if comment.user == request.user:
        messages.error(request, "You cannot report your own comment.")
        return redirect("feed:feed_home")

    Report.objects.create(
        reporter=request.user,
        target_type=Report.TARGET_COMMENT,
        reported_user=comment.user,
        comment=comment,
        post=comment.post,
        reason=request.POST.get("reason", Report.REASON_INAPPROPRIATE),
        details=request.POST.get("details", "").strip(),
    )

    messages.success(request, "Comment report submitted. Our team will review it.")
    return redirect("feed:feed_home")