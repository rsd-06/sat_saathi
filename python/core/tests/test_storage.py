from __future__ import annotations

import io
from pathlib import Path

import pytest

from satsaathi_core.storage import (
    LocalStorage,
    S3Storage,
    StorageError,
    build_storage,
)


def test_round_trips_bytes(tmp_path: Path):
    store = LocalStorage(tmp_path)
    store.put("assets/a.tif", b"hello")

    assert store.get("assets/a.tif") == b"hello"
    assert store.exists("assets/a.tif")


def test_round_trips_a_file_object(tmp_path: Path):
    store = LocalStorage(tmp_path)
    store.put("assets/b.tif", io.BytesIO(b"stream"))

    assert store.get("assets/b.tif") == b"stream"


def test_creates_nested_directories(tmp_path: Path):
    store = LocalStorage(tmp_path)
    store.put("a/b/c/d.tif", b"x")

    assert (tmp_path / "a" / "b" / "c" / "d.tif").exists()


def test_delete_is_idempotent(tmp_path: Path):
    store = LocalStorage(tmp_path)
    store.put("x.tif", b"x")
    store.delete("x.tif")
    store.delete("x.tif")

    assert not store.exists("x.tif")


def test_missing_key_raises(tmp_path: Path):
    store = LocalStorage(tmp_path)

    with pytest.raises(StorageError):
        store.get("nope.tif")
    with pytest.raises(StorageError):
        store.local_path("nope.tif")


@pytest.mark.parametrize(
    "key", ["../escape.tif", "a/../../escape.tif", "/etc/passwd", "", "   "]
)
def test_rejects_keys_that_escape_the_root(tmp_path: Path, key: str):
    # Keys arrive from request payloads, so traversal must never reach disk.
    store = LocalStorage(tmp_path)

    with pytest.raises(StorageError):
        store.put(key, b"x")


def test_local_path_is_usable_by_rasterio(tmp_path: Path, optical: Path):
    store = LocalStorage(tmp_path)
    store.put("scene.tif", optical.read_bytes())

    from satsaathi_core.raster import inspect

    assert inspect(store.local_path("scene.tif")).band_count == 4


def test_url_is_served_under_the_base_path(tmp_path: Path):
    store = LocalStorage(tmp_path, base_url="/files")
    assert store.url("a/b.tif") == "/files/a/b.tif"


class FakeS3:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def put_object(self, Bucket, Key, Body):  # noqa: N803 - boto3 signature
        self.objects[Key] = Body

    def get_object(self, Bucket, Key):  # noqa: N803
        if Key not in self.objects:
            raise KeyError(Key)
        return {"Body": io.BytesIO(self.objects[Key])}

    def head_object(self, Bucket, Key):  # noqa: N803
        if Key not in self.objects:
            raise KeyError(Key)

    def delete_object(self, Bucket, Key):  # noqa: N803
        self.objects.pop(Key, None)


def test_s3_backend_satisfies_the_same_contract(tmp_path: Path):
    store = S3Storage("bucket", client=FakeS3(), cache_dir=tmp_path / "cache")
    store.put("k.tif", b"payload")

    assert store.get("k.tif") == b"payload"
    assert store.exists("k.tif")
    # local_path materialises the object so rasterio can open it.
    assert store.local_path("k.tif").read_bytes() == b"payload"

    store.delete("k.tif")
    assert not store.exists("k.tif")


def test_offline_mode_refuses_the_s3_backend(tmp_path: Path):
    with pytest.raises(StorageError, match="offline"):
        build_storage("s3", local_root=tmp_path, bucket="b", offline=True)


def test_build_storage_returns_local_backend(tmp_path: Path):
    store = build_storage("local", local_root=tmp_path, bucket=None, offline=True)
    assert isinstance(store, LocalStorage)


def test_unknown_backend_is_rejected(tmp_path: Path):
    with pytest.raises(StorageError, match="unknown"):
        build_storage("ftp", local_root=tmp_path, bucket=None, offline=False)
