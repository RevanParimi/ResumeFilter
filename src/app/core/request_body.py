"""Bound raw HTTP input before framework JSON parsing and route work."""

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def refuse() -> None:
            await JSONResponse(status_code=413, content={
                "detail": f"request body exceeds max_request_body_bytes={self.max_bytes}",
            })(scope, receive, send)

        # Content-Length is an early refusal hint, never an allocation size or
        # framing authority. Compare decimal bytes without converting an
        # untrusted, potentially enormous integer. Count the actual body below
        # even for missing, malformed or underreported lengths.
        limit = str(self.max_bytes).encode("ascii")
        for name, value in scope.get("headers", ()):
            if name.lower() == b"content-length":
                value = value.strip()
                digits = value.lstrip(b"0")
                if value.isdigit() and (len(digits) > len(limit) or (
                    len(digits) == len(limit) and digits > limit
                )):
                    await refuse()
                    return

        # A bytearray avoids retained per-event metadata for empty/tiny chunks.
        # The server already owns the current ASGI event; do not copy/retain it
        # if it would cross the cap. JSON/decoded objects have separate bounds.
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                # Complete the outer request-context middleware too. The client
                # may already be gone, so delivery of this response is best-effort.
                await JSONResponse(status_code=400, content={
                    "detail": "request_body_incomplete",
                })(scope, receive, send)
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > self.max_bytes:
                await refuse()
                return
            body.extend(chunk)
            if not message.get("more_body", False):
                break

        buffered: Message | None = {"type": "http.request", "body": bytes(body), "more_body": False}
        del body, message, chunk

        async def replay() -> Message:
            nonlocal buffered
            if buffered is not None:
                message, buffered = buffered, None
                return message
            return await receive()

        await self.app(scope, replay, send)
