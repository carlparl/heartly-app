import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from chat.routing import websocket_urlpatterns as chat_websocket_urlpatterns
from notifications.routing import websocket_urlpatterns as notification_websocket_urlpatterns
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "heartly.settings")

django_asgi_app = get_asgi_application()

import chat.routing
import notifications.routing

websocket_urlpatterns = (
    chat_websocket_urlpatterns
    + notification_websocket_urlpatterns
)

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AuthMiddlewareStack(
            URLRouter(websocket_urlpatterns)
        ),
    }
)