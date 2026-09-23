"""Grouping assets into something analysable, and saying whether it is."""

from __future__ import annotations

import uuid
from dataclasses import asdict

from fastapi import APIRouter, status
from sqlalchemy.orm import selectinload

from satsaathi_core import compatibility
from satsaathi_core.models import Asset, InputMode, InputSet, InputSetAsset
from satsaathi_core.raster import BandInfo, RasterMetadata, SensorType

from ..deps import Session, SettingsDep, api_error
from ..schemas import CheckOut, InputSetIn, InputSetOut

router = APIRouter(prefix="/input-sets", tags=["input-sets"])

REQUIRED_ROLES: dict[str, tuple[str, ...]] = {
    "single": ("single",),
    "fusion": ("optical", "sar"),
    "change": ("before", "after"),
}


def _sensor_type(value: str | None) -> SensorType:
    """Narrow the stored string back to the literal the dataclass declares."""
    return value if value in ("optical", "sar") else "unknown"  # type: ignore[return-value]


def _as_metadata(asset: Asset) -> RasterMetadata:
    """Rebuild the inspection result from what was persisted at upload."""
    return RasterMetadata(
        driver="GTiff",
        width=asset.width or 0,
        height=asset.height or 0,
        band_count=len(asset.bands or []),
        dtype="unknown",
        crs=asset.crs,
        pixel_size=(asset.pixel_size or 0.0, asset.pixel_size or 0.0),
        bands=[
            BandInfo(
                index=b["index"],
                description=b.get("description"),
                dtype=b.get("dtype", "unknown"),
                nodata=b.get("nodata"),
                role=b.get("role"),
            )
            for b in (asset.bands or [])
        ],
        sensor_type=_sensor_type(asset.sensor_type),
        acquired_at=asset.acquired_at,
        footprint=_footprint_geojson(asset),
        warnings=list(asset.warnings or []),
    )


def _footprint_geojson(asset: Asset) -> dict | None:
    if asset.footprint is None:
        return None
    from geoalchemy2.shape import to_shape
    from shapely.geometry import mapping

    return mapping(to_shape(asset.footprint))


@router.post("", response_model=InputSetOut, status_code=status.HTTP_201_CREATED)
async def create_input_set(
    session: Session, settings: SettingsDep, body: InputSetIn
) -> InputSetOut:
    required = REQUIRED_ROLES[body.mode]
    missing = [r for r in required if r not in body.assets]
    if missing or set(body.assets) - set(required):
        raise api_error(
            status.HTTP_400_BAD_REQUEST,
            "inputSet.error.wrongRoles",
            mode=body.mode,
            expected=list(required),
            given=sorted(body.assets),
        )

    assets: dict[str, Asset] = {}
    for role, asset_id in body.assets.items():
        asset = await session.get(Asset, asset_id)
        if asset is None:
            raise api_error(
                status.HTTP_404_NOT_FOUND, "asset.not_found", id=str(asset_id)
            )
        assets[role] = asset

    metas = {role: _as_metadata(a) for role, a in assets.items()}

    if body.mode == "single":
        checks = compatibility.check_single(metas["single"])
    elif body.mode == "fusion":
        checks = compatibility.check_fusion(
            metas["optical"],
            metas["sar"],
            min_overlap_pct=settings.pair_min_overlap_pct,
        )
    else:
        checks = compatibility.check_change(
            metas["before"],
            metas["after"],
            min_overlap_pct=settings.pair_min_overlap_pct,
        )

    input_set = InputSet(
        mode=InputMode(body.mode), checks=[asdict(c) for c in checks]
    )
    session.add(input_set)
    await session.flush()

    for role, asset in assets.items():
        session.add(
            InputSetAsset(
                input_set_id=input_set.id, asset_id=asset.id, role=role
            )
        )
    await session.flush()

    return InputSetOut(
        id=input_set.id,
        mode=body.mode,
        assets={role: a.id for role, a in assets.items()},
        checks=[CheckOut(**asdict(c)) for c in checks],
        blocked=compatibility.blocked(checks),
        created_at=input_set.created_at,
    )


@router.get("/{input_set_id}", response_model=InputSetOut)
async def get_input_set(session: Session, input_set_id: uuid.UUID) -> InputSetOut:
    from sqlalchemy import select

    result = await session.scalars(
        select(InputSet)
        .where(InputSet.id == input_set_id)
        .options(selectinload(InputSet.assets))
    )
    input_set = result.first()
    if input_set is None:
        raise api_error(
            status.HTTP_404_NOT_FOUND, "inputSet.not_found", id=str(input_set_id)
        )

    checks = [CheckOut(**c) for c in (input_set.checks or [])]
    return InputSetOut(
        id=input_set.id,
        mode=input_set.mode.value,
        assets={a.role.value: a.asset_id for a in input_set.assets},
        checks=checks,
        blocked=any(c.status == "fail" for c in checks),
        created_at=input_set.created_at,
    )
