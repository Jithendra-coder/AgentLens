"""Request IDs, bounded body buffering, and safe structured request logging."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from agentlens.logging import set_correlation_id, set_request_id

from .errors import GatewayError, error_response_body

logger = logging.getLogger("agentlens.gateway")


class RequestMiddleware:
    """Assign request IDs, propagate correlation IDs, and enforce bounded body reads."""

    def __init__(self, app: ASGIApp, *, max_request_bytes: int) -> None:
        self.app = app
        self.max_request_bytes = max_request_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid4())
        correlation_id = None
        for raw_header, raw_value in scope.get("headers", []):
            if raw_header.lower() == b"x-correlation-id":
                try:
                    correlation_id = raw_value.decode("ascii").strip()
                except Exception:
                    correlation_id = None
                break
        if not correlation_id:
            correlation_id = request_id

        set_request_id(request_id)
        set_correlation_id(correlation_id)

        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        state["correlation_id"] = correlation_id
        started = time.monotonic()
        status_code = 500

        async def send_with_context(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("ascii")))
                if correlation_id:
                    headers.append((b"x-correlation-id", correlation_id.encode("ascii")))
                headers.append((b"x-content-type-options", b"nosniff"))
                headers.append((b"x-frame-options", b"DENY"))
                headers.append((b"x-xss-protection", b"1; mode=block"))
                headers.append((b"referrer-policy", b"strict-origin-when-cross-origin"))
                message = {**message, "headers": headers}
            await send(message)

        try:
            if scope.get("method") in {"POST", "PUT", "PATCH"}:
                body = await self._read_bounded(receive)
                if body is None:
                    error = GatewayError(
                        code="payload_too_large",
                        message="Request body exceeds the configured limit.",
                        status_code=413,
                    )
                    await self._send_error(send_with_context, error, request_id)
                    return

                sent = False

                async def replay_body() -> Message:
                    nonlocal sent
                    if sent:
                        return {"type": "http.disconnect"}
                    sent = True
                    return {"type": "http.request", "body": body, "more_body": False}

                await self.app(scope, replay_body, send_with_context)
            else:
                await self.app(scope, receive, send_with_context)
        finally:
            duration_s = time.monotonic() - started
            duration_ms = round(duration_s * 1000, 3)
            route = str(scope.get("path", ""))
            method = str(scope.get("method", "GET"))
            logger.info(
                "gateway_request",
                extra={
                    "request_id": request_id,
                    "correlation_id": correlation_id,
                    "route": route,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                },
            )
            try:
                from agentlens.telemetry import get_metrics_registry

                get_metrics_registry().record_http_request(route, method, status_code, duration_s)
            except Exception:
                pass
            set_request_id(None)
            set_correlation_id(None)

    async def _read_bounded(self, receive: Receive) -> bytes | None:
        chunks: list[bytes] = []
        total = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                break
            if message["type"] != "http.request":
                continue
            chunk = message.get("body", b"")
            total += len(chunk)
            if total > self.max_request_bytes:
                return None
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        return b"".join(chunks)

    async def _send_error(
        self,
        send: Callable[[Message], Awaitable[None]],
        error: GatewayError,
        request_id: str,
    ) -> None:
        import json

        body = json.dumps(error_response_body(error, request_id), separators=(",", ":")).encode()
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode("ascii")),
        ]
        await send({"type": "http.response.start", "status": error.status_code, "headers": headers})
        await send({"type": "http.response.body", "body": body})
