"""Regenerate the index golden fixtures from the *training scripts*.

    uv run python infra/fixtures/golden/indices/make_fixtures.py \
        path/to/satquery_ndvi_train.py path/to/satquery_ndwi_train.py

The SHARED CONTRACT block is cut out of each script's source and executed on
its own, so the fixtures come from the functions the adapters were trained
with, not from our copy of them. The script's torch import is never run.

Inputs are seeded pseudo-random Sentinel-2 L1C-like digital numbers, with a
few NaN pixels, because edge handling is where a re-implementation drifts.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
MARK = "# SHARED CONTRACT"


def contract_namespace(script: Path) -> dict:
    src = script.read_text(encoding="utf-8")
    start = src.rindex("\n", 0, src.index(MARK)) - 95  # include the ==== rule
    start = src.rindex("# ====", 0, src.index(MARK))
    end = src.index("return f\"Image 1", start)
    end = src.index("\n", end) + 1
    ns: dict = {}
    exec(  # noqa: S102 - the whole point is to run the script's own code
        "import numpy as np\nfrom PIL import Image\nfrom scipy import ndimage as ndi\n"
        + src[start:end],
        ns,
    )
    return ns


def bands(seed: int, side: int = 64) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:side, 0:side] / side
    base = {
        "blue": 900 + 300 * xx,
        "green": 1000 + 600 * yy,
        "red": 800 + 900 * (1 - xx) * yy,
        "nir": 1500 + 2500 * xx * (1 - yy),
        "swir1": 1200 + 800 * yy,
    }
    out = {}
    for role, arr in base.items():
        noisy = arr + rng.normal(0, 120, arr.shape)
        noisy = noisy.astype(np.float32)
        noisy[rng.random(arr.shape) < 0.01] = np.nan
        out[role] = noisy
    # A patch of "water": green above NIR and SWIR.
    out["nir"][40:56, 4:20] = 300
    out["swir1"][40:56, 4:20] = 250
    return out


def main(ndvi_script: Path, ndwi_script: Path) -> None:
    ndvi = contract_namespace(ndvi_script)
    ndwi_ns = contract_namespace(ndwi_script)
    ndwi_src = ndwi_script.read_text(encoding="utf-8")
    assert "(MNDWI water fraction: {mndwi_water}%.)" in ndwi_src

    question = "Where is the densest vegetation? Mark it."
    for seed in (7, 11):
        roles = bands(seed)
        case = HERE / f"seed{seed}"
        case.mkdir(exist_ok=True)
        np.savez(case / "bands.npz", **roles)
        b = {"B02": roles["blue"], "B03": roles["green"], "B04": roles["red"],
             "B08": roles["nir"], "B11": roles["swir1"]}

        # NaN -> uint8 is undefined behaviour inside `true_colour`, and EuroSAT
        # never had nodata, so the backend zero-fills before calling it.
        b_rgb = {k: np.nan_to_num(v, nan=0.0) for k, v in b.items()}
        ndvi["true_colour"](b_rgb).save(case / "true_colour.png")
        x = ndvi["compute_index"]("NDVI", b)
        ndvi["render_index"](x, ndvi["NDVI_LUT"]).save(case / "ndvi_map.png")
        s = ndvi["index_stats"]("NDVI", x, ndvi["NDVI_BINS"])
        (case / "ndvi_prompt.txt").write_text(ndvi["build_prompt"](question, s), encoding="utf-8")
        boxes = ndvi["mask_boxes"](x > 0.6, "dense vegetation")

        w = ndwi_ns["compute_index"]("NDWI", b)
        m = ndwi_ns["compute_index"]("MNDWI", b)
        ndwi_ns["render_index"](w, ndwi_ns["NDWI_LUT"]).save(case / "ndwi_map.png")
        sw = ndwi_ns["index_stats"]("NDWI", w, ndwi_ns["NDWI_BINS"])
        mw = round(100 * float(np.nanmean(m > 0)), 1)
        water_q = "Is there water in this scene?"
        prompt = ndwi_ns["build_prompt"](water_q, sw) + f"\n(MNDWI water fraction: {mw}%.)"
        (case / "ndwi_prompt.txt").write_text(prompt, encoding="utf-8")

        (case / "expected.json").write_text(
            json.dumps(
                {
                    "ndvi_question": question,
                    "ndwi_question": water_q,
                    "ndvi_stats": s,
                    "ndvi_stats_text": ndvi["stats_text"](s),
                    "ndvi_dense_boxes": boxes,
                    "ndwi_stats": sw,
                    "ndwi_stats_text": ndwi_ns["stats_text"](sw),
                    "mndwi_water_pct": mw,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print("wrote", case)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
