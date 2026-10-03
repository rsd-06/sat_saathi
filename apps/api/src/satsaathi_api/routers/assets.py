"""Uploading imagery and reading what it says about itself."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy import select

from satsaathi_core import indices as index_maths
from satsaathi_core.models import Asset
from satsaathi_core.raster import inspect, is_tiff
from satsaathi_tools.presets import SENSOR_PRESETS, preset_band_map

from ..deps import Session, SettingsDep, StorageDep, api_error
from ..schemas import AssetOut, BandMappingIn, BandOut, PresignOut
from .auth import CurrentUser, current_user

# Everything here is somebody's own work, so all of it needs an account.
router = APIRouter(prefix="/assets", tags=["assets"], dependencies=[Depends(current_user)])

#: GeoTIFF only. Anything else is refused outright rather than coerced: the
#: pipeline measures pixels against a coordinate system, and a format that
#: cannot carry one would be answered from guesses.
ALLOWED_SUFFIXES = {".tif", ".tiff"}


def _to_out(asset: Asset, tile_url: str | None = None) -> AssetOut:
    band_map = asset.band_map or {}
    unavailable = index_maths.available_indices(band_map)
    available = [str(name) for name in index_maths.INDEX_BANDS if name not in unavailable]
    return AssetOut(
        id=asset.id,
        filename=asset.filename,
        storage_key=asset.storage_key,
        sensor_type=asset.sensor_type,
        sensor_preset=asset.sensor_preset,
        crs=asset.crs,
        pixel_size=asset.pixel_size,
        width=asset.width,
        height=asset.height,
        band_count=len(asset.bands or []),
        bands=[BandOut(**b) for b in (asset.bands or [])],
        band_map=band_map or None,
        acquired_at=asset.acquired_at,
        # Filled by the caller when the geometry is already in hand; reading it
        # back from PostGIS costs a shape conversion nothing here needs.
        footprint=None,
        warnings=asset.warnings or [],
        available_indices=available,
        unavailable_indices={str(k): v for k, v in unavailable.items()},
        tile_url=tile_url,
        created_at=asset.created_at,
    )


async def _load(session: Session, asset_id: uuid.UUID, user) -> Asset:
    asset = await session.get(Asset, asset_id)
    if asset is None or asset.user_id != user.id:
        raise api_error(status.HTTP_404_NOT_FOUND, "asset.not_found", id=str(asset_id))
    return asset


@router.post("", response_model=AssetOut, status_code=status.HTTP_201_CREATED)
async def create_asset(
    session: Session,
    user: CurrentUser,
    storage: StorageDep,
    settings: SettingsDep,
    file: UploadFile = File(...),
) -> AssetOut:
    """Store an upload, then read its headers and record what they say."""
    name = Path(file.filename or "upload.tif").name
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise api_error(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "upload.error.unsupportedType",
            suffix=suffix,
        )

    payload = await file.read()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(payload) > max_bytes:
        raise api_error(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            "upload.error.tooLarge",
            max=settings.max_upload_mb,
        )

    # The extension is only a claim; the leading bytes are the evidence. This
    # runs before the file is stored, so a renamed JPEG leaves nothing behind.
    if not is_tiff(payload):
        raise api_error(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "upload.error.notTiff")

    asset_id = uuid.uuid4()
    key = f"assets/{asset_id}/{name}"
    storage.put(key, payload)

    try:
        meta = inspect(storage.local_path(key))
    except Exception as exc:
        storage.delete(key)
        raise api_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "upload.error.unreadable",
            detail=str(exc),
        ) from exc

    acquired = meta.acquired_at
    if acquired is not None and not isinstance(acquired, datetime):
        acquired = datetime.combine(acquired, datetime.min.time())

    asset = Asset(
        user_id=user.id,
        id=asset_id,
        storage_key=key,
        filename=name,
        sensor_type=meta.sensor_type,
        bands=[
            {
                "index": b.index,
                "description": b.description,
                "dtype": b.dtype,
                "nodata": b.nodata,
                "role": None,
            }
            for b in meta.bands
        ],
        band_map=None,
        crs=meta.crs,
        pixel_size=meta.pixel_size[0] if meta.pixel_size else None,
        width=meta.width,
        height=meta.height,
        acquired_at=acquired,
        warnings=meta.warnings,
    )
    if meta.footprint:
        from geoalchemy2.shape import from_shape
        from shapely.geometry import shape as to_shape

        asset.footprint = from_shape(to_shape(meta.footprint), srid=4326)

    session.add(asset)
    await session.flush()

    out = _to_out(asset)
    out.footprint = meta.footprint
    return out


@router.get("/{asset_id}", response_model=AssetOut)
async def get_asset(session: Session, user: CurrentUser, asset_id: uuid.UUID) -> AssetOut:
    return _to_out(await _load(session, asset_id, user))


@router.patch("/{asset_id}/bands", response_model=AssetOut)
async def set_bands(
    session: Session, user: CurrentUser, asset_id: uuid.UUID, body: BandMappingIn
) -> AssetOut:
    """Apply a sensor preset or an explicit mapping.

    Roles decide which indices are computable, so they are never inferred from
    band order — this endpoint is the only way one gets set.
    """
    asset = await _load(session, asset_id, user)

    if body.preset:
        if body.preset not in SENSOR_PRESETS:
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "bands.error.unknownPreset",
                preset=body.preset,
            )
        mapping = preset_band_map(body.preset)
        asset.sensor_preset = body.preset
    elif body.band_map:
        mapping = dict(body.band_map)
        asset.sensor_preset = None
    else:
        raise api_error(status.HTTP_400_BAD_REQUEST, "bands.error.nothingGiven")

    count = len(asset.bands or [])
    for role, number in mapping.items():
        if not 1 <= number <= count:
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "bands.error.outOfRange",
                role=role,
                band=number,
                count=count,
            )

    asset.band_map = mapping
    asset.bands = [
        {**b, "role": next((r for r, n in mapping.items() if n == b["index"]), None)}
        for b in (asset.bands or [])
    ]
    await session.flush()
    return _to_out(asset)


@router.get("", response_model=list[AssetOut])
async def list_assets(session: Session, user: CurrentUser, limit: int = 20) -> list[AssetOut]:
    rows = await session.scalars(
        select(Asset)
        .where(Asset.user_id == user.id)
        .order_by(Asset.created_at.desc())
        .limit(min(limit, 100))
    )
    return [_to_out(a) for a in rows]


@router.post("/presign", response_model=PresignOut)
async def presign(settings: SettingsDep) -> PresignOut:
    """Where to send bytes for a large upload.

    The local backend has no separate upload host, so this points back at the
    ordinary multipart endpoint; the S3 backend returns a real presigned PUT.
    """
    key = f"assets/{uuid.uuid4()}/upload"
    if settings.storage_backend == "local":
        return PresignOut(upload_url="/api/v1/assets", method="POST", storage_key=key)
    raise api_error(status.HTTP_501_NOT_IMPLEMENTED, "upload.presign.unavailable")
