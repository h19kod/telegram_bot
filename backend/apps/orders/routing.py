from django.urls import path

from apps.orders.consumers import OrdersConsumer

websocket_urlpatterns = [
    path("ws/b/<uuid:business_id>/", OrdersConsumer.as_asgi()),
]
