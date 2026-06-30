from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from accounts.models import CustomUser
from .models import Like, Match
import json

@login_required
def discover(request):
    """
    Main discover page - shows potential matches for the current user.
    Later we will:
      - Fetch real profiles from the Profile model
      - Apply AI matching / filtering
      - Support swipe actions
    """
    context = {
        "page_title": "Discover",
        # Placeholder - will be replaced with real queryset later
        "potential_matches": [],  
    }
    return render(request, "matches/discover.html", context)


@login_required
def like_user(request, user_id):
    """Handle right swipe / like"""
    if request.method == "POST":
        try:
            to_user = CustomUser.objects.get(id=user_id)
            Like.objects.get_or_create(from_user=request.user, to_user=to_user)

            if Like.objects.filter(from_user=to_user, to_user=request.user).exists():
                Match.objects.get_or_create(
                    user1=min(request.user, to_user, key=lambda u: u.id),
                    user2=max(request.user, to_user, key=lambda u: u.id)
                )
                return JsonResponse({
                    'status': 'match',
                    'matched_user_id': to_user.id
                })

            return JsonResponse({'status': 'liked'})

        except Exception as e:
            return JsonResponse({'status': 'error'}, status=400)

    return JsonResponse({'status': 'invalid'}, status=400)


@login_required
def pass_user(request, user_id):
    """Handle left swipe / pass"""
    if request.method == "POST":
        return JsonResponse({'status': 'passed'})
    return JsonResponse({'status': 'invalid'}, status=400)


@login_required
def super_like(request, user_id):
    """Handle super like (up swipe)"""
    if request.method == "POST":
        try:
            to_user = CustomUser.objects.get(id=user_id)
            Like.objects.get_or_create(from_user=request.user, to_user=to_user)

            if Like.objects.filter(from_user=to_user, to_user=request.user).exists():
                Match.objects.get_or_create(
                    user1=min(request.user, to_user, key=lambda u: u.id),
                    user2=max(request.user, to_user, key=lambda u: u.id)
                )
                return JsonResponse({
                    'status': 'match',
                    'matched_user_id': to_user.id
                })

            return JsonResponse({'status': 'super_liked'})

        except Exception as e:
            return JsonResponse({'status': 'error'}, status=400)

    return JsonResponse({'status': 'invalid'}, status=400)


@login_required
def match_screen(request, user_id=None):
    """Show 'It's a Match!' screen with the actual matched user"""
    if user_id:
        try:
            matched_user = CustomUser.objects.get(id=user_id)
        except CustomUser.DoesNotExist:
            matched_user = CustomUser.objects.exclude(id=request.user.id).order_by('?').first()
    else:
        matched_user = CustomUser.objects.exclude(id=request.user.id).order_by('?').first()

    main_photo = matched_user.photos.filter(is_main=True).first() if matched_user else None
    matched_photo_url = main_photo.image.url if main_photo else "https://picsum.photos/id/1005/300/300"

    return render(request, 'heartly/match.html', {
        'matched_user': matched_user,
        'matched_photo': matched_photo_url
    })