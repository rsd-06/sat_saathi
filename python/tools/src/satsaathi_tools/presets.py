"""Sensor band layouts.

Band order is a property of the product, not something to infer from the file,
so each preset states which 1-based band carries which role. Anything not
listed here needs a manual mapping — guessing would silently produce a wrong
index, which is the one failure the product exists to avoid.
"""

from __future__ import annotations

#: preset key -> {role: 1-based band number}
SENSOR_PRESETS: dict[str, dict[str, int]] = {
    # Sentinel-2 L2A, 10 m bands subset as commonly exported.
    "sentinel-2-l2a": {"blue": 1, "green": 2, "red": 3, "nir": 4, "swir1": 5},
    # Landsat 8/9 OLI surface reflectance, bands 2-6.
    "landsat-8-9-oli": {"blue": 1, "green": 2, "red": 3, "nir": 4, "swir1": 5},
    # Resourcesat-2 LISS-III: green, red, NIR, SWIR — no blue band.
    "resourcesat-2-liss3": {"green": 1, "red": 2, "nir": 3, "swir1": 4},
    # Resourcesat LISS-IV: green, red, NIR only.
    "resourcesat-liss4": {"green": 1, "red": 2, "nir": 3},
    # Cartosat-2S multispectral.
    "cartosat-2s-mx": {"blue": 1, "green": 2, "red": 3, "nir": 4},
    # SAR products carry polarisations rather than spectral bands.
    "sentinel-1-grd": {"vv": 1, "vh": 2},
    "eos-04-risat": {"vv": 1, "vh": 2},
}

#: Human-facing labels live in the i18n catalogs; this is only the key list.
PRESET_KEYS = tuple(SENSOR_PRESETS)


def preset_band_map(preset: str) -> dict[str, int]:
    return dict(SENSOR_PRESETS[preset])
