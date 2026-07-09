from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache


@never_cache
def service_worker(request):
    """
    Serve the root-scoped service worker at /sw.js.
    A service worker served from /static/ can only control /static/, so keep this at root.
    """
    sw_path = Path(settings.BASE_DIR) / "static" / "sw.js"

    try:
        script = sw_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        script = "self.addEventListener('install', function(event) { self.skipWaiting(); });"

    response = HttpResponse(script, content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


def manifest(request):
    """
    Compatibility route for /manifest.webmanifest.
    The same manifest also exists as /static/manifest.webmanifest.
    """
    manifest_path = Path(settings.BASE_DIR) / "static" / "manifest.webmanifest"

    try:
        content = manifest_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        content = "{}"

    response = HttpResponse(content, content_type="application/manifest+json")
    response["Cache-Control"] = "no-cache"
    return response


def offline(request):
    return render(request, "pwa/offline.html")
