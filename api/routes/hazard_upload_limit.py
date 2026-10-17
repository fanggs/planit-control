"""Bound request bodies before FastAPI buffers JSON or spools multipart files."""

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.formparsers import MultiPartException

from api.routes.hazard_errors import HazardRoute


class _BodyLimitExceeded(MultiPartException):
    """A parser-compatible error makes multipart close its temporary files."""


def _too_large_response() -> JSONResponse:
    return JSONResponse(
        status_code=413,
        content={"error": {
            "code": "payload_too_large", "message": "Request body is too large.",
        }},
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


class BodyLimitedHazardRoute(HazardRoute):
    """Subclass with max_body_bytes for a route-specific total request limit.

    The declared Content-Length is only an early rejection hint. Counting
    actual ASGI body chunks also covers chunked or misleading-length requests.
    This is an application limit; keep a reverse-proxy limit as defense in depth.
    """

    max_body_bytes: int

    def get_route_handler(self):
        original_handler = super().get_route_handler()
        limit = self.max_body_bytes
        if type(limit) is not int or limit <= 0:
            raise ValueError("max_body_bytes must be a positive integer")

        async def handler(request: Request):
            if request.method not in {"POST", "PATCH", "PUT"}:
                return await original_handler(request)
            try:
                declared_size = int(request.headers.get("content-length", ""))
            except ValueError:
                declared_size = None
            if declared_size is not None and declared_size > limit:
                return _too_large_response()

            received = 0
            exceeded = False

            async def bounded_receive():
                nonlocal received, exceeded
                message = await request.receive()
                if message["type"] == "http.request":
                    received += len(message.get("body", b""))
                    if received > limit:
                        exceeded = True
                        # Older Starlette versions close multipart files only
                        # on MultiPartException, not on arbitrary HTTP errors.
                        raise _BodyLimitExceeded("Request body is too large.")
                return message

            bounded_request = Request(request.scope, receive=bounded_receive)
            response = await original_handler(bounded_request)
            # FastAPI/Starlette translate parser errors to 400; only this known
            # overflow becomes 413. Other malformed inputs keep their own errors.
            return _too_large_response() if exceeded else response

        return handler
