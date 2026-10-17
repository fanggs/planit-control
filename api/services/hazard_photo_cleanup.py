"""Plan and remove old, unattached private photo uploads.

Upload and report creation are separate requests, so a failed report can leave
an orphan image. This maintenance helper uses the app's existing DB session and
is dry-run by default. Apply it only while report/photo API workers are stopped:
otherwise a report could attach a key between the DB check and file removal.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from api.services.hazard_photo_service import PhotoNotFound, PrivatePhotoStore
from api.services.hazard_report_service import is_photo_attached


MINIMUM_AGE = timedelta(hours=24)


def old_unattached_photo_keys(
    store: PrivatePhotoStore,
    session: Any,
    *,
    now: datetime | None = None,
    minimum_age: timedelta = MINIMUM_AGE,
    attached: Callable[[Any, str], bool] = is_photo_attached,
) -> list[str]:
    """Read-only list of complete, old uploads that no report references."""
    if minimum_age < MINIMUM_AGE:
        raise ValueError("Photo retention must be at least 24 hours")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must include a timezone")
    cutoff = now.timestamp() - minimum_age.total_seconds()
    keys: list[str] = []
    for metadata in store.root.glob("*.json"):
        key = metadata.stem
        if not store._valid_key(key):
            continue
        data = store.root / f"{key}.bin"
        try:
            info = (metadata.lstat(), data.lstat())
        except OSError:
            continue
        if any(
            not stat.S_ISREG(item.st_mode)
            or stat.S_IMODE(item.st_mode) != 0o600
            or item.st_uid != os.geteuid()
            or item.st_mtime > cutoff
            for item in info
        ):
            continue
        try:
            store.read(key)  # Verify the sidecar, bytes, and checksum before considering removal.
        except PhotoNotFound:
            continue
        if not attached(session, key):
            keys.append(key)
    return sorted(keys)


def clean_old_unattached_photos(
    store: PrivatePhotoStore,
    session: Any,
    *,
    apply: bool = False,
    api_stopped: bool = False,
    now: datetime | None = None,
    minimum_age: timedelta = MINIMUM_AGE,
    attached: Callable[[Any, str], bool] = is_photo_attached,
) -> list[str]:
    """Return candidates on dry-run; remove only with an explicit stopped-API assertion.

    This function targets exact key-derived files inside the dedicated private
    directory. It never deletes report rows or photos attached to a report.
    """
    if apply and not api_stopped:
        raise ValueError("Stop all report/photo API workers before applying photo cleanup")
    candidates = old_unattached_photo_keys(
        store, session, now=now, minimum_age=minimum_age, attached=attached,
    )
    if not apply:
        return candidates
    removed: list[str] = []
    for key in candidates:
        # Recheck against the same session immediately before removing bytes.
        if attached(session, key):
            continue
        (store.root / f"{key}.bin").unlink()
        (store.root / f"{key}.json").unlink()
        removed.append(key)
    return removed
