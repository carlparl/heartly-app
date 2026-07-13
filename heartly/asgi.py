import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "heartly.settings")

from django.core.asgi import get_asgi_application

# Initialize Django before importing any routing modules that load models.
django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator

from chat.routing import websocket_urlpatterns as chat_websocket_urlpatterns
from notifications.routing import (
    websocket_urlpatterns as notification_websocket_urlpatterns,
)

websocket_urlpatterns = (
    list(chat_websocket_urlpatterns)
    + list(notification_websocket_urlpatterns)
)

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            AuthMiddlewareStack(
                URLRouter(websocket_urlpatterns)
            )
        ),
    }
)