# Mock files

Real satellite data, clipped small enough to commit, so you can try SatSaathi without hunting for imagery. These are **not** synthetic: every pixel was measured by a Copernicus Sentinel satellite. Each is a valid GeoTIFF that the upload check accepts, and each carries band names and scene details in its tags (`gdalinfo` shows them).

| File | Sensor | Size | What it is for |
|---|---|---|---|
| `sentinel2_dhubri_dry_20191226.tif` | Sentinel-2 L2A, 5 bands | 614 x 568 px, 10 m, 1 MB | The Brahmaputra at Dhubri, Assam, in the dry season. Clear sky (0% cloud/shadow in the clip). |
| `sentinel2_dhubri_wet_20200802.tif` | Sentinel-2 L2A, 5 bands | same grid, 1 MB | The same place in the 2020 monsoon. About 6% of the clip is cloud. Pairs with the file above for **change detection**. |
| `sentinel2_farmland_ndvi_20191226.tif` | Sentinel-2 L2A, 5 bands | 640 x 640 px, 10 m, 2.5 MB | Green farmland and forest near 26.15 N, 90.2 E. Use for **NDVI / vegetation** questions. |
| `sentinel1_dhubri_flood_20200725.tif` | Sentinel-1 RTC, VV + VH | 614 x 568 px, 10 m, 2.3 MB | Radar over the same area on 2020-07-25, eight days before the monsoon optical scene. Radar sees through cloud. Use for **SAR water** questions. |

The two Dhubri optical files share one grid, so they overlay exactly.

## Band order

The optical files hold bands in the order SatSaathi's `sentinel-2-l2a` preset expects: 1 blue (B02), 2 green (B03), 3 red (B04), 4 NIR (B08), 5 SWIR1 (B11, resampled from 20 m to 10 m). Values are surface reflectance times 10,000 (`uint16`). The radar file is `float32` linear power (dB = 10 log10 x) in the `sentinel-1-grd` order: 1 VV, 2 VH.

If the app does not pick the sensor itself, choose the matching preset in the workspace.

## Things to try

- **Vegetation** (`farmland`): "How green is this area?" or "What is the average NDVI?"
- **Water** (`dhubri_dry` or `dhubri_wet`): "How much of this area is water?"
- **Change** (both Dhubri optical files): the same ground on two dates, with about 2,450 ha more water in the monsoon scene. The workspace takes one GeoTIFF at a time; the Image stack panel compares two images in the browser but takes PNG/JPEG, not TIFF.
- **SAR** (`sentinel1`): "Where is the water?" The model path needs the GPU weights; without them the answer is labelled as a stand-in, and the measured numbers still come from the pixels.

## Rough reference numbers

Computed independently with a plain NDVI / NDWI at threshold 0 on the full clip, so you can sanity-check what the app reports. The app's own masking and thresholds can differ a little, so expect the same ballpark, not identical digits.

| File | Mean NDVI | Area with NDWI > 0 |
|---|---|---|
| dhubri_dry | 0.13 | about 560 ha (16%) |
| dhubri_wet | -0.11 | about 3,010 ha (86%) |
| farmland | 0.41 | about 37 ha (1%) |

Water that is present in the wet clip and absent in the dry one: about 2,450 ha.

## Provenance and licence

- Sentinel-2: contains modified Copernicus Sentinel data 2019 and 2020, via [Earth Search](https://earth-search.aws.element84.com/v1) (AWS Open Data). Scenes `S2B_45RZJ_20191226_1_L2A` and `S2B_45RZJ_20200802_1_L2A`.
- Sentinel-1: contains modified Copernicus Sentinel data 2020, radiometrically terrain-corrected, via [Microsoft Planetary Computer](https://planetarycomputer.microsoft.com/dataset/sentinel-1-rtc). Scene `S1A_IW_GRDH_1SDV_20200725T120517_20200725T120542_033611_03E538_rtc`.
- Copernicus Sentinel data is free to use, including commercially, with attribution. These clips keep that attribution here. They are exempt from this repository's MIT licence.
