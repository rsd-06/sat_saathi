"""Where uploaded imagery and produced artifacts live.

Two backends behind one protocol: the local filesystem (the default, and the
only one offline mode permits) and any S3-compatible store. Callers deal in
opaque keys and never in paths, so nothing above this module knows which
backend is in use.
"""

from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO


class StorageError(RuntimeError):
    pass


class Storage(ABC):
    @abstractmethod
    def put(self, key: str, data: BinaryIO | bytes) -> str:
        """Store bytes under `key` and return the key."""

    @abstractmethod
    def get(self, key: str) -> bytes: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def local_path(self, key: str) -> Path:
        """A real filesystem path, so rasterio can open the object.

        An S3 backend downloads to a cache directory to honour this; GDAL's
        /vsis3/ would avoid the copy but ties raster reads to the backend.
        """

    @abstractmethod
    def url(self, key: str) -> str:
        """A URL the tiler or the browser can fetch."""


def _safe_key(key: str) -> str:
    """Reject traversal before it reaches the filesystem.

    Absolute-looking keys are refused rather than quietly rewritten to a
    relative path: a leading slash or a drive letter in a storage key means
    a caller bug or an attack, and normalising it away hides both.
    """
    cleaned = key.strip()
    if (
        not cleaned
        or cleaned.startswith(("/", "\\"))
        or ".." in Path(cleaned).parts
        or Path(cleaned).is_absolute()
        or (len(cleaned) > 1 and cleaned[1] == ":")  # Windows drive letter
    ):
        raise StorageError(f"unsafe storage key: {key!r}")
    return cleaned


class LocalStorage(Storage):
    def __init__(self, root: Path | str, base_url: str = "/files"):
        self.root = Path(root)
        self.base_url = base_url.rstrip("/")
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = self.root / _safe_key(key)
        # Defence in depth: resolve and confirm containment.
        resolved = path.resolve()
        if not resolved.is_relative_to(self.root.resolve()):
            raise StorageError(f"key escapes storage root: {key!r}")
        return resolved

    def put(self, key: str, data: BinaryIO | bytes) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as handle:
            if isinstance(data, bytes):
                handle.write(data)
            else:
                shutil.copyfileobj(data, handle)
        return key

    def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.exists():
            raise StorageError(f"no such key: {key}")
        return path.read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def local_path(self, key: str) -> Path:
        path = self._path(key)
        if not path.exists():
            raise StorageError(f"no such key: {key}")
        return path

    def url(self, key: str) -> str:
        return f"{self.base_url}/{_safe_key(key)}"


class S3Storage(Storage):
    """S3-compatible backend. Refuses to construct in offline mode."""

    def __init__(
        self,
        bucket: str,
        *,
        client=None,
        cache_dir: Path | str = ".cache/s3",
        public_base_url: str | None = None,
    ):
        if client is None:  # pragma: no cover - exercised only with boto3 present
            # Optional extra: `satsaathi-core[s3]`. Kept out of the base install
            # so the offline image never pulls an AWS SDK it must not use.
            import boto3  # pyright: ignore[reportMissingImports]

            client = boto3.client("s3")
        self.bucket = bucket
        self.client = client
        self.cache_dir = Path(cache_dir)
        self.public_base_url = public_base_url

    def put(self, key: str, data: BinaryIO | bytes) -> str:
        safe = _safe_key(key)
        body = data if isinstance(data, bytes) else data.read()
        self.client.put_object(Bucket=self.bucket, Key=safe, Body=body)
        return key

    def get(self, key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=_safe_key(key))
        return response["Body"].read()

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=_safe_key(key))
            return True
        except Exception:
            return False

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=_safe_key(key))

    def local_path(self, key: str) -> Path:
        safe = _safe_key(key)
        path = self.cache_dir / safe
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(self.get(safe))
        return path

    def url(self, key: str) -> str:
        safe = _safe_key(key)
        if self.public_base_url:
            return f"{self.public_base_url.rstrip('/')}/{safe}"
        return self.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": safe}, ExpiresIn=3600
        )


def build_storage(
    backend: str, *, local_root: Path | str, bucket: str | None, offline: bool
) -> Storage:
    """Construct the configured backend, enforcing the offline guarantee."""
    if backend == "local":
        return LocalStorage(local_root)
    if backend == "s3":
        if offline:
            raise StorageError(
                "offline mode forbids the s3 storage backend; use local"
            )
        if not bucket:
            raise StorageError("s3 storage backend requires a bucket name")
        return S3Storage(bucket)
    raise StorageError(f"unknown storage backend: {backend!r}")
