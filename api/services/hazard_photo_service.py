"""Private API photo storage; report rows supply the site's photo association.

Uploads have no site_id. The report service verifies uploader ownership before
attaching a key. DeepSpace carries notifications, never these image bytes.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import secrets
import stat
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from api.schemas.hazard_report import validate_reporter_id


MAX_PHOTO_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
MAX_IMAGE_SIDE = 10_000
_REPOSITORY = Path(__file__).resolve().parents[2]


class PhotoTooLarge(ValueError):
    """The image exceeds the upload byte limit."""


class InvalidPhoto(ValueError):
    """The image is not a supported, complete, bounded JPEG or PNG."""


class PhotoNotFound(LookupError):
    """The key or its required private metadata is unavailable."""


class PhotoStorageUnavailable(RuntimeError):
    """Private storage could not accept an upload."""


@dataclass(frozen=True)
class StoredPhoto:
    data: bytes
    content_type: str
    uploader_id: str


def _image_content_type(data: bytes) -> str:
    if not data:
        raise InvalidPhoto("Select a JPEG or PNG image")
    if len(data) > MAX_PHOTO_BYTES:
        raise PhotoTooLarge("Photos must be 5 MB or smaller")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data), formats=("JPEG", "PNG")) as image:
                image_format = image.format
                width, height = image.size
                if (
                    width < 1 or height < 1
                    or max(width, height) > MAX_IMAGE_SIDE
                    or width * height > MAX_IMAGE_PIXELS
                    or getattr(image, "n_frames", 1) != 1
                ):
                    raise InvalidPhoto("Use a single image of at most 20 megapixels")
                image.verify()
            # verify() checks structure; loading rejects truncated pixel data too.
            with Image.open(io.BytesIO(data), formats=("JPEG", "PNG")) as image:
                image.load()
    except InvalidPhoto:
        raise
    except (
        UnidentifiedImageError, OSError, ValueError, SyntaxError,
        Image.DecompressionBombError, Image.DecompressionBombWarning,
    ):
        raise InvalidPhoto("Upload a complete JPEG or PNG image") from None
    return "image/jpeg" if image_format == "JPEG" else "image/png"


class PrivatePhotoStore:
    """Store on a dedicated, persistent private server volume.

    Never mount this directory as static content. Bytes and metadata use
    owner-only permissions, and client filenames never become storage paths.
    """

    def __init__(self, root: str | Path):
        requested = Path(root).expanduser()
        if requested.is_symlink():
            raise ValueError("Photo storage must be a dedicated private directory")
        self.root = requested.resolve()
        public_page = (_REPOSITORY / "page").resolve()
        if self.root == public_page or public_page in self.root.parents:
            raise ValueError("Photo storage cannot be inside the public page directory")
        if self.root == Path.home() or self.root == _REPOSITORY or self.root in _REPOSITORY.parents:
            raise ValueError("Choose a dedicated photo directory, not a broad existing directory")
        if self.root.exists() and not self.root.is_dir():
            raise ValueError("Photo storage must be a directory")
        self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        info = self.root.lstat()
        # Never chmod an existing path: a mistaken setting might name shared
        # data. The operator must deliberately create a private directory.
        if (
            not stat.S_ISDIR(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o700
            or info.st_uid != os.geteuid()
        ):
            raise ValueError("Photo storage must be owned by the API user with permissions 0700")

    @staticmethod
    def _valid_key(key: str) -> bool:
        return isinstance(key, str) and 1 <= len(key) <= 1024 and re.fullmatch(r"[A-Za-z0-9_-]+", key) is not None

    @staticmethod
    def _write_private(path: Path, data: bytes) -> None:
        # Exclusive creation never overwrites another key or follows a symlink.
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        except OSError:
            # This call created path; a partial write must not remain readable.
            try:
                path.unlink()
            except OSError:
                pass
            raise

    def save(self, data: bytes, uploader_id: str) -> str:
        uploader_id = validate_reporter_id(uploader_id)
        content_type = _image_content_type(data)
        key = secrets.token_urlsafe(32)
        data_path = self.root / f"{key}.bin"
        metadata_path = self.root / f"{key}.json"
        metadata = json.dumps(
            {
                "version": 1, "key": key, "uploader_id": uploader_id,
                "content_type": content_type, "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            },
            ensure_ascii=True,
        ).encode("utf-8")
        created: list[Path] = []
        try:
            self._write_private(data_path, data)
            created.append(data_path)
            self._write_private(metadata_path, metadata)
            created.append(metadata_path)
        except OSError:
            for path in created:
                try:
                    path.unlink()
                except OSError:
                    pass
            raise PhotoStorageUnavailable("Photo storage is temporarily unavailable") from None
        return key

    @staticmethod
    def _read_private(path: Path, limit: int) -> bytes:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > limit or stat.S_IMODE(info.st_mode) & 0o077:
                raise PhotoNotFound("Photo not found")
            data = stream.read(limit + 1)
            if len(data) > limit:
                raise PhotoNotFound("Photo not found")
            return data

    def read(self, key: str) -> StoredPhoto:
        if not self._valid_key(key):
            raise PhotoNotFound("Photo not found")
        try:
            metadata = json.loads(self._read_private(self.root / f"{key}.json", 4096))
            if (
                not isinstance(metadata, dict)
                or metadata.get("version") != 1
                or metadata.get("key") != key
                or metadata.get("content_type") not in {"image/jpeg", "image/png"}
                or type(metadata.get("size")) is not int
                or not 1 <= metadata["size"] <= MAX_PHOTO_BYTES
            ):
                raise PhotoNotFound("Photo not found")
            uploader_id = validate_reporter_id(metadata["uploader_id"])
            data = self._read_private(self.root / f"{key}.bin", MAX_PHOTO_BYTES)
            if len(data) != metadata["size"] or hashlib.sha256(data).hexdigest() != metadata.get("sha256"):
                raise PhotoNotFound("Photo not found")
            return StoredPhoto(data=data, content_type=metadata["content_type"], uploader_id=uploader_id)
        except (OSError, ValueError, TypeError, KeyError):
            # Missing or damaged sidecars never grant access to raw bytes.
            raise PhotoNotFound("Photo not found") from None

    def verify_photo(self, db: Any, key: str, subject: str, site_id: int) -> bool:
        """Match save_report's verifier interface without a separate DB engine.

        The route checks site existence; the report row supplies site association.
        The contract allows upload reuse and does not define single-use keys.
        """
        if type(site_id) is not int or site_id <= 0:
            return False
        try:
            return self.read(key).uploader_id == validate_reporter_id(subject)
        except (PhotoNotFound, ValueError):
            return False
