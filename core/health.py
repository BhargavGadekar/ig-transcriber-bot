"""Minimal asyncio HTTP health-check endpoint (no extra dependencies).

GET /health → 200 with a JSON stats document; anything else → 404.
Binds to 127.0.0.1 so it works inside Docker (HEALTHCHECK) without exposing
anything publicly.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable

log = logging.getLogger(__name__)


async def start_health_server(
    port: int, stats_fn: Callable[[], dict]
) -> asyncio.AbstractServer:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request_line = await asyncio.wait_for(reader.readline(), timeout=10)
            parts = request_line.decode("latin1", errors="replace").split()
            path = parts[1] if len(parts) > 1 else "/"
            while True:
                try:
                    line = await asyncio.wait_for(reader.readline(), timeout=0.5)
                    if not line or line in (b"\r\n", b"\n"):
                        break
                except asyncio.TimeoutError:
                    break
            if path == "/health":
                body = json.dumps(stats_fn(), ensure_ascii=False).encode("utf-8")
                header = (
                    "HTTP/1.1 200 OK\r\n"
                    "Content-Type: application/json\r\n"
                    f"Content-Length: {len(body)}\r\n"
                    "Connection: close\r\n\r\n"
                ).encode("ascii")
            else:
                body = b'{"error":"not found"}'
                header = (
                    "HTTP/1.1 404 Not Found\r\n"
                    "Content-Type: application/json\r\n"
                    f"Content-Length: {len(body)}\r\n"
                    "Connection: close\r\n\r\n"
                ).encode("ascii")
            writer.write(header + body)
            await writer.drain()
        except (ConnectionError, asyncio.TimeoutError, asyncio.CancelledError):
            pass
        except Exception:
            log.exception("health server handler error")
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except (ConnectionError, asyncio.CancelledError):
                pass

    server = await asyncio.start_server(handle, "127.0.0.1", port)
    log.info("health check listening on 127.0.0.1:%d/health", port)
    return server
