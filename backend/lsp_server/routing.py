"""
Django Channels WebSocket URL routing for SyntaxTide LSP proxy.
"""

from django.urls import path

from lsp_server.consumers import LSPProxyConsumer

websocket_urlpatterns = [
    path('ws/lsp/<str:language>/', LSPProxyConsumer.as_asgi()),
]
