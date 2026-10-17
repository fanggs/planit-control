"""Authenticated photo routes, registered in the team's existing FastAPI app."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from api.auth.hazard_auth import Principal, require_roles
from api.routes.hazard_upload_limit import BodyLimitedHazardRoute
from api.services.hazard_photo_service import (
    MAX_PHOTO_BYTES, InvalidPhoto, PhotoNotFound, PhotoStorageUnavailable,
    PhotoTooLarge, PrivatePhotoStore,
)


class PhotoUploadResponse(BaseModel):
    photo_key: str


# Keep room for the multipart boundary and headers without allowing unbounded
# extra parts. The actual image still has its own strict 5 MiB limit below.
MAX_PHOTO_REQUEST_BYTES = MAX_PHOTO_BYTES + 64 * 1024


class PhotoRoute(BodyLimitedHazardRoute):
    max_body_bytes = MAX_PHOTO_REQUEST_BYTES


def create_photo_router(
    *, get_db: Callable, get_principal: Callable, store: PrivatePhotoStore,
    is_photo_attached: Callable[[Any, str], bool],
) -> APIRouter:
    """Inject database/auth dependencies; no second app or database connection.

    Both roles see photos attached to reports. Only the uploader may preview
    an unattached photo. is_photo_attached queries persisted hazard_reports.
    """
    if not callable(is_photo_attached) or any(
        inspect.iscoroutinefunction(candidate) or inspect.isasyncgenfunction(candidate)
        for candidate in (is_photo_attached, getattr(is_photo_attached, "__call__", None))
    ):
        raise ValueError("is_photo_attached must be a synchronous database callback")
    router = APIRouter(tags=["Hazard photos"], route_class=PhotoRoute)

    @router.post("/photos", response_model=PhotoUploadResponse, status_code=201)
    async def upload_photo(
        file: UploadFile = File(...),
        principal: Principal = Depends(get_principal),
    ):
        require_roles(principal, "crew", "supervisor")
        try:
            # PhotoRoute limits the complete request before multipart parsing.
            # This second limit applies specifically to the selected image.
            data = await file.read(MAX_PHOTO_BYTES + 1)
            if len(data) > MAX_PHOTO_BYTES:
                raise PhotoTooLarge("Photos must be 5 MB or smaller")
            key = await run_in_threadpool(store.save, data, principal.sub)
        except PhotoTooLarge:
            raise HTTPException(413, {"code": "photo_too_large", "message": "Photos must be 5 MB or smaller"}) from None
        except InvalidPhoto as exc:
            raise HTTPException(415, {"code": "invalid_photo", "message": str(exc)}) from None
        except PhotoStorageUnavailable:
            raise HTTPException(503, "Photo storage is temporarily unavailable") from None
        except OSError:
            raise HTTPException(503, "Photo upload is temporarily unavailable") from None
        finally:
            await file.close()
        return PhotoUploadResponse(photo_key=key)

    @router.get("/photos/{photo_key}")
    def view_photo(
        photo_key: str,
        principal: Principal = Depends(get_principal),
        db: Any = Depends(get_db),
    ):
        require_roles(principal, "crew", "supervisor")
        try:
            photo = store.read(photo_key)
        except PhotoNotFound:
            raise HTTPException(404, "Photo not found") from None
        if photo.uploader_id != principal.sub:
            try:
                attached = is_photo_attached(db, photo_key)
            except SQLAlchemyError:
                raise HTTPException(503, "Photo access verification is temporarily unavailable") from None
            if inspect.isawaitable(attached):
                if inspect.iscoroutine(attached):
                    attached.close()
                raise HTTPException(503, "Photo access verification is temporarily unavailable")
            if attached is not True:
                raise HTTPException(404, "Photo not found")
        extension = "jpg" if photo.content_type == "image/jpeg" else "png"
        return Response(
            photo.data, media_type=photo.content_type,
            headers={
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
                "Content-Disposition": f'inline; filename="photo.{extension}"',
            },
        )

    return router
