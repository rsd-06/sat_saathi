"""Images and prompts, prepared exactly as the adapters were trained."""

from __future__ import annotations

import json

import numpy as np
import pytest
import rasterio
from PIL import Image
from rasterio.transform import from_origin

from satsaathi_core import imaging, vlm_prompts


class TestFit:
    def test_large_images_shrink_to_512_on_the_long_side(self):
        out = imaging.fit(Image.new("RGB", (2048, 1024)))

        assert out.size == (512, 256)

    def test_small_images_are_never_upscaled(self):
        assert imaging.fit(Image.new("RGB", (300, 200))).size == (300, 200)

    def test_grey_becomes_three_channels(self):
        assert imaging.fit(Image.new("L", (64, 64))).mode == "RGB"


class TestSar:
    def test_an_8bit_chip_passes_through(self, tmp_path):
        arr = (np.arange(64 * 64) % 256).astype(np.uint8).reshape(64, 64)
        path = tmp_path / "chip.png"
        Image.fromarray(arr).save(path)

        prepared = imaging.load_sar(path)

        assert prepared.image.size == (64, 64)
        assert np.array_equal(np.asarray(prepared.image)[..., 0], arr)
        assert prepared.crs is None
        assert prepared.notes == ["imaging.sar_8bit_chip"]

    def test_a_raw_geotiff_goes_through_db_and_a_percentile_stretch(self, tmp_path):
        rng = np.random.default_rng(0)
        linear = rng.gamma(4, 0.05, (100, 100)).astype("float32")
        path = tmp_path / "s1.tif"
        with rasterio.open(
            path, "w", driver="GTiff", width=100, height=100, count=1, dtype="float32",
            crs="EPSG:32643", transform=from_origin(500000, 4000000, 10, 10),
        ) as dst:
            dst.write(linear, 1)

        prepared = imaging.load_sar(path)

        expected = imaging.stretch_to_uint8(10 * np.log10(linear.astype("float64")))
        assert np.array_equal(np.asarray(prepared.image)[..., 0], expected)
        assert prepared.crs == "EPSG:32643"
        assert prepared.transform[0] == 10.0
        assert prepared.notes == ["imaging.sar_db_stretch"]

    def test_values_already_in_db_are_not_converted_twice(self):
        db = np.array([[-20.0, -5.0]])

        assert np.array_equal(imaging.to_db(db), db)


class TestPrompts:
    def test_the_system_prompt_is_the_one_in_the_meta(self, tmp_path):
        system = "You are SatQuery-SAR, an expert analyst ..."
        (tmp_path / "meta.json").write_text(json.dumps({"system_prompt": system}))

        meta = vlm_prompts.load_meta(tmp_path / "meta.json")
        msgs = vlm_prompts.messages(meta["system_prompt"], 1, "Where is the ship?")

        assert msgs == [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": [{"type": "image"}, {"type": "text", "text": "Where is the ship?"}],
            },
        ]

    def test_images_come_before_the_text(self):
        msgs = vlm_prompts.messages("s", 2, "q")

        assert [c["type"] for c in msgs[1]["content"]] == ["image", "image", "text"]

    def test_a_meta_without_a_system_prompt_is_refused(self, tmp_path):
        (tmp_path / "meta.json").write_text("{}")

        with pytest.raises(vlm_prompts.MetaError):
            vlm_prompts.load_meta(tmp_path / "meta.json")

    def test_the_change_prompt_comes_from_the_optical_meta(self):
        meta = {"change_prompt": "The first image is BEFORE and the second image is AFTER, "
                                 "same location. {q}"}

        text = vlm_prompts.change_text(meta, "What changed?")

        assert text == (
            "The first image is BEFORE and the second image is AFTER, same location. "
            "What changed?"
        )

    def test_the_explain_prompt_starts_with_the_trained_change_prompt(self):
        meta = {"change_prompt": "BEFORE/AFTER. {q}"}
        regions = [{"bbox_2d": [1, 2, 3, 4]}]

        text = vlm_prompts.change_explain_text(meta, "What changed?", regions)

        assert text.startswith("BEFORE/AFTER. What changed?\n")
        assert "[1, 2, 3, 4]" in text
