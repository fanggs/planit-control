"""Report endpoints wired to the team's session, Auth0 and alert services.

Alan registers the returned router after removing the old sample GET /reports.
The supplied session must belong to this request. These routes commit database
work themselves; no module here creates an engine or a separate application.
"""

from collections.abc import Callable
import inspect
import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import BigInteger, Column, MetaData, Table, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from api.auth.hazard_auth import Principal, require_roles
from api.routes.hazard_upload_limit import BodyLimitedHazardRoute
from api.schemas.hazard_report import (
    HazardReportCreate, HazardReportRead, HazardReportResolve,
)
from api.services.hazard_report_service import (
    PhotoReferenceNotAuthorized, PhotoVerifier, ReportChange, ReportNotFound,
    WarningAlertIntegrationMissing, WarningWriter,
    get_site_reports, resolve_report, save_report,
)


logger = logging.getLogger(__name__)
EventPublisher = Callable[[str, dict], None]
_sites = Table(
    "sites", MetaData(), Column("site_id", BigInteger, primary_key=True),
    schema="public",
)


class HazardReportRoute(BodyLimitedHazardRoute):
    # The longest valid description, even JSON-escaped Unicode, fits well
    # below this cap. Reject oversized JSON before buffering or DB access.
    max_body_bytes = 64 * 1024


def _require_site(db: Session, site_id: int) -> None:
    if db.execute(select(_sites.c.site_id).where(_sites.c.site_id == site_id)).scalar_one_or_none() is None:
        raise HTTPException(404, f"Site {site_id} not found")


def _raise_database_error(exc: Exception) -> None:
    # Database exception strings can contain report text and bound parameters.
    logger.error("Report operation failed (%s)", type(exc).__name__)
    if isinstance(exc, IntegrityError):
        raise HTTPException(409, "The report could not be saved with these references.") from exc
    if isinstance(exc, SQLAlchemyError):
        raise HTTPException(503, "Report storage is temporarily unavailable.") from exc
    raise HTTPException(500, "The report operation could not be completed.") from exc


def _publish_change(publish: EventPublisher, change: ReportChange, *, created: bool) -> None:
    if not change.changed:
        return
    report = change.report
    payload = {"report_id": str(report.id), "site_id": report.site_id}
    if created:
        payload["created_at"] = report.created_at.isoformat().replace("+00:00", "Z")
    events = [("report.created" if created else "report.resolved", payload)]
    if change.warning_alert_id is not None:
        alert_id = change.warning_alert_id
        if isinstance(alert_id, UUID):
            alert_id = str(alert_id)
        events.append(("alert.started" if created else "alert.cleared", {
            "alert_id": alert_id, "site_id": report.site_id,
        }))
    for name, event_payload in events:
        try:
            result = publish(name, event_payload)
            if inspect.isawaitable(result) or inspect.isasyncgen(result):
                if inspect.iscoroutine(result):
                    result.close()
                raise TypeError("publish_event must perform synchronous delivery or enqueueing")
        except Exception as exc:
            # The database transaction already committed. Returning a write
            # failure here could prompt a duplicate report on a client retry.
            logger.error("Committed report event %s was not delivered (%s)", name, type(exc).__name__)


def create_report_router(
    *,
    get_db: Callable,
    get_principal: Callable,
    verify_photo: PhotoVerifier,
    start_warning: WarningWriter,
    clear_warning: WarningWriter,
    publish_event: EventPublisher,
) -> APIRouter:
    """Build routes using real shared dependencies, or explicit test doubles.

    Warning writers use the passed Session and must never commit independently.
    The publisher is synchronous; Alan can enqueue delivery in his adapter.
    """
    if (
        not callable(publish_event)
        or inspect.iscoroutinefunction(publish_event)
        or inspect.isasyncgenfunction(publish_event)
        or inspect.iscoroutinefunction(getattr(publish_event, "__call__", None))
        or inspect.isasyncgenfunction(getattr(publish_event, "__call__", None))
    ):
        raise ValueError("publish_event must be a synchronous event publisher")
    router = APIRouter(tags=["hazard reports"], route_class=HazardReportRoute)

    @router.get("/reports", response_model=list[HazardReportRead])
    def list_reports(
        site_id: Annotated[int, Query(gt=0, le=9223372036854775807)],
        db: Session = Depends(get_db),
        principal: Principal = Depends(get_principal),
    ):
        require_roles(principal, "crew", "supervisor")
        try:
            _require_site(db, site_id)
            return get_site_reports(db, site_id)
        except SQLAlchemyError as exc:
            db.rollback()
            _raise_database_error(exc)

    @router.post("/reports", response_model=HazardReportRead, status_code=201)
    def create_report(
        body: HazardReportCreate,
        db: Session = Depends(get_db),
        principal: Principal = Depends(get_principal),
    ):
        require_roles(principal, "crew", "supervisor")
        try:
            _require_site(db, body.site_id)
            change = save_report(
                db, body, reporter_id=principal.sub, verify_photo=verify_photo,
                start_warning=start_warning,
            )
            db.commit()
        except HTTPException:
            db.rollback()
            raise
        except PhotoReferenceNotAuthorized as exc:
            db.rollback()
            raise HTTPException(403, "Photo is not an authorized private upload.") from exc
        except WarningAlertIntegrationMissing as exc:
            db.rollback()
            raise HTTPException(503, "Report warning integration is unavailable.") from exc
        except Exception as exc:
            db.rollback()
            _raise_database_error(exc)
        _publish_change(publish_event, change, created=True)
        return change.report

    @router.patch("/reports/{report_id}", response_model=HazardReportRead)
    def resolve_existing_report(
        report_id: UUID,
        body: HazardReportResolve,
        db: Session = Depends(get_db),
        principal: Principal = Depends(get_principal),
    ):
        require_roles(principal, "supervisor")
        try:
            change = resolve_report(
                db, report_id, resolved_by=principal.sub, clear_warning=clear_warning,
            )
            db.commit()
        except ReportNotFound as exc:
            db.rollback()
            raise HTTPException(404, "Report not found.") from exc
        except WarningAlertIntegrationMissing as exc:
            db.rollback()
            raise HTTPException(503, "Report warning integration is unavailable.") from exc
        except Exception as exc:
            db.rollback()
            _raise_database_error(exc)
        _publish_change(publish_event, change, created=False)
        return change.report

    return router
