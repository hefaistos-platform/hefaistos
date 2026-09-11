"""
Django Channels WebSocket consumer that proxies JSON-RPC messages
between the Monaco Editor and local SyntaxTide LSP servers.
"""

import asyncio
import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger(__name__)


class LSPProxyConsumer(AsyncWebsocketConsumer):
    """Proxy WebSocket messages between Monaco Editor and a local LSP server.

    The LSP server speaks the standard LSP protocol over TCP (Content-Length
    framed JSON-RPC).  This consumer bridges the browser WebSocket connection
    to that TCP socket, translating between raw JSON-RPC (WebSocket side) and
    the Content-Length framed format (TCP side).
    """

    async def connect(self):
        self.language = self.scope['url_route']['kwargs']['language']

        from lsp_server.manager import get_lsp_manager
        manager = get_lsp_manager()
        port = manager.language_ports.get(self.language)

        if port is None:
            logger.error("LSPProxyConsumer: unknown language '%s'", self.language)
            await self.close()
            return

        await self.accept()

        # Establish TCP connection to the local LSP server process
        try:
            self.reader, self.writer = await asyncio.open_connection('127.0.0.1', port)
            logger.info(
                "LSPProxyConsumer: connected to %s LSP on port %d", self.language, port
            )
        except OSError as exc:
            logger.error(
                "LSPProxyConsumer: failed to connect to %s LSP on port %d: %s",
                self.language, port, exc,
            )
            await self.close()
            return

        # Start background task that forwards LSP server responses to the browser
        self._read_task = asyncio.ensure_future(self._forward_lsp_to_ws())

    async def disconnect(self, close_code):
        if hasattr(self, '_read_task') and not self._read_task.done():
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass

        if hasattr(self, 'writer'):
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass

    async def receive(self, text_data=None, bytes_data=None):
        """Forward a JSON-RPC message from the browser to the LSP server."""
        if not hasattr(self, 'writer'):
            return

        payload = text_data or (bytes_data.decode('utf-8') if bytes_data else None)
        if payload is None:
            return

        try:
            # Validate the incoming data is valid JSON before forwarding
            json.loads(payload)
            encoded = payload.encode('utf-8')
            header = f'Content-Length: {len(encoded)}\r\n\r\n'.encode('ascii')
            self.writer.write(header + encoded)
            await self.writer.drain()
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("LSPProxyConsumer: error forwarding to LSP: %s", exc)

    async def _forward_lsp_to_ws(self):
        """Read LSP server responses and forward them to the browser."""
        try:
            while True:
                # Read headers until we find the blank line separating header from body
                raw_header = await self.reader.readuntil(b'\r\n\r\n')
                header_text = raw_header.decode('ascii', errors='replace')

                content_length: int | None = None
                for line in header_text.splitlines():
                    if line.lower().startswith('content-length:'):
                        try:
                            content_length = int(line.split(':', 1)[1].strip())
                        except ValueError:
                            pass

                if content_length is None:
                    logger.error(
                        "LSPProxyConsumer: missing Content-Length header from %s LSP",
                        self.language,
                    )
                    break

                body = await self.reader.readexactly(content_length)
                await self.send(text_data=body.decode('utf-8'))
        except asyncio.IncompleteReadError:
            logger.warning(
                "LSPProxyConsumer: %s LSP server closed the connection unexpectedly "
                "(it may have crashed or restarted)",
                self.language,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "LSPProxyConsumer: error reading from %s LSP: %s", self.language, exc
            )
        finally:
            await self.close()
