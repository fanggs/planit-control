"""One explicit integration hook for Aryan's report and photo routers.

Nothing is registered or connected at import time. Alan calls this with the
existing FastAPI app and request-scoped database session dependency.
"""

from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI

from api.auth.hazard_auth import Auth0Config, create_auth_dependency
from api.routes.hazard_photos import create_photo_router
from api.routes.hazard_reports import EventPublisher, create_report_router
from api.services.hazard_photo_service import PrivatePhotoStore
from api.services.hazard_report_service import WarningWriter, is_photo_attached


def _route_paths(routes, prefix: str = ""):
    """Read both flattened and lazy-included FastAPI routers.

    FastAPI versions differ in how include_router stores routes. Recurse into
    included routers and mounts so a hidden/sample route cannot bypass the
    duplicate check simply by being included rather than decorated on app.
    """
    for route in routes:
        original = getattr(route, "original_router", None)
        if original is not None:
            context = getattr(route, "include_context", None)
            yield from _route_paths(original.routes, prefix + getattr(context, "prefix", ""))
            continue
        path = prefix + getattr(route, "path", "")
        yield path
        children = getattr(route, "routes", None)
        if children is not None:
            yield from _route_paths(children, path)


def register_hazard_reporting(
    app: FastAPI,
    *,
    get_db: Callable,
    start_warning: WarningWriter,
    clear_warning: WarningWriter,
    publish_event: EventPublisher,
    photo_directory: str | Path,
    auth_config: Auth0Config | None = None,
) -> PrivatePhotoStore:
    """Register the protected routes after the old sample route is removed.

    The directory must be private persistent storage outside all static roots.
    This function does not create a database engine, tables, or an application.
    """
    # A duplicate sample route could shadow authentication based on route order.
    conflicts = [
        path for path in _route_paths(app.routes)
        if path in {"/reports", "/photos"}
        or path.startswith(("/reports/", "/photos/"))
    ]
    if conflicts:
        raise ValueError(
            "Remove existing report/photo routes before registering Aryan's routers: "
            + ", ".join(conflicts)
        )
    get_principal = create_auth_dependency(auth_config or Auth0Config.from_env())
    store = PrivatePhotoStore(photo_directory)
    app.include_router(create_report_router(
        get_db=get_db, get_principal=get_principal, verify_photo=store.verify_photo,
        start_warning=start_warning, clear_warning=clear_warning,
        publish_event=publish_event,
    ))
    app.include_router(create_photo_router(
        get_db=get_db, get_principal=get_principal, store=store,
        is_photo_attached=is_photo_attached,
    ))
    return store
