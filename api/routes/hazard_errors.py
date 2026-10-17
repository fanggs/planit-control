"""Keep report/photo failures in the contract's error envelope.

This route class is scoped to Aryan's routers, so it does not replace Alan's
application-wide error handlers or expose submitted values in validation errors.
"""

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute


class HazardRoute(APIRoute):
    def get_route_handler(self):
        original_handler = super().get_route_handler()

        async def handler(request: Request):
            try:
                return await original_handler(request)
            except RequestValidationError:
                return JSONResponse(
                    status_code=422,
                    content={"error": {
                        "code": "validation_error",
                        "message": "Request fields are missing or invalid.",
                    }},
                )
            except HTTPException as exc:
                codes = {
                    400: "bad_request", 401: "unauthorized", 403: "forbidden",
                    404: "not_found", 409: "conflict", 413: "payload_too_large",
                    415: "unsupported_media_type", 422: "validation_error",
                    503: "unavailable",
                }
                if isinstance(exc.detail, dict):
                    error = {
                        "code": exc.detail.get("code", codes.get(exc.status_code, "error")),
                        "message": exc.detail.get("message", "Request failed."),
                    }
                else:
                    error = {
                        "code": codes.get(exc.status_code, "error"),
                        "message": str(exc.detail),
                    }
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"error": error},
                    headers=exc.headers,
                )

        return handler
