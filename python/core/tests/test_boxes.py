"""Reading boxes out of model text, and moving them between frames."""

from __future__ import annotations

from satsaathi_core.boxes import (
    box_f1,
    iou,
    parse_boxes,
    pixels_to_map,
    pixels_to_relative,
    relative_to_pixels,
)


class TestParse:
    def test_the_trained_fenced_format(self):
        text = '```json\n[{"bbox_2d": [100, 200, 300, 400], "label": "ship"}]\n```'

        assert parse_boxes(text) == [{"bbox_2d": [100, 200, 300, 400], "label": "ship"}]

    def test_bare_json_with_surrounding_prose(self):
        text = 'Here it is: [{"bbox_2d": [1, 2, 30, 40], "label": "car"}] done.'

        assert parse_boxes(text)[0]["bbox_2d"] == [1, 2, 30, 40]

    def test_output_truncated_mid_list_keeps_the_complete_boxes(self):
        text = (
            '```json\n[{"bbox_2d": [10, 20, 110, 120], "label": "ship"}, '
            '{"bbox_2d": [500, 500, 600, 600], "label": "sh'
        )

        boxes = parse_boxes(text)

        assert [b["bbox_2d"] for b in boxes] == [[10, 20, 110, 120], [500, 500, 600, 600]]
        assert boxes[0]["label"] == "ship"

    def test_a_label_written_before_the_box(self):
        text = '[{"label": "tank", "bbox_2d": [5, 5, 50, 50]'

        assert parse_boxes(text) == [{"bbox_2d": [5, 5, 50, 50], "label": "tank"}]

    def test_out_of_range_and_reversed_coordinates_are_normalised(self):
        text = '[{"bbox_2d": [1200, 300, -5, 100], "label": "x"}]'

        assert parse_boxes(text)[0]["bbox_2d"] == [0, 100, 1000, 300]

    def test_degenerate_boxes_are_dropped(self):
        assert parse_boxes('[{"bbox_2d": [10, 10, 10, 50]}]') == []

    def test_prose_without_boxes_gives_nothing(self):
        assert parse_boxes("There is a ship near the harbour.") == []

    def test_a_missing_label_gets_a_neutral_one(self):
        assert parse_boxes('"bbox_2d": [1, 1, 9, 9]')[0]["label"] == "object"


class TestFrames:
    def test_relative_to_pixels_uses_the_original_size(self):
        # The model saw a 512 px copy; boxes go back onto the upload.
        assert relative_to_pixels([0, 0, 500, 250], 2000, 1000) == [0, 0, 1000, 250]

    def test_pixels_to_relative_round_trips(self):
        assert pixels_to_relative([100, 50, 200, 100], 400, 200) == [250, 250, 500, 500]

    def test_no_crs_means_no_map_coordinates(self):
        transform = (10.0, 0.0, 500000.0, 0.0, -10.0, 4000000.0)

        assert pixels_to_map([0, 0, 10, 10], transform, None) is None
        assert pixels_to_map([0, 0, 10, 10], None, "EPSG:32643") is None

    def test_pixels_to_map_applies_the_affine(self):
        transform = (10.0, 0.0, 500000.0, 0.0, -10.0, 4000000.0)

        assert pixels_to_map([0, 0, 10, 20], transform, "EPSG:32643") == [
            500000.0,
            3999800.0,
            500100.0,
            4000000.0,
        ]


class TestAgreement:
    def test_iou(self):
        assert iou([0, 0, 10, 10], [5, 0, 15, 10]) == 50 / 150

    def test_f1_of_identical_sets_is_one(self):
        boxes = [[0, 0, 10, 10], [20, 20, 30, 30]]

        assert box_f1(boxes, boxes) == 1.0

    def test_f1_of_disjoint_sets_is_zero(self):
        assert box_f1([[0, 0, 10, 10]], [[50, 50, 60, 60]]) == 0.0

    def test_f1_partial(self):
        pred = [[0, 0, 10, 10], [50, 50, 60, 60]]
        ref = [[0, 0, 10, 10]]

        assert round(box_f1(pred, ref), 3) == round(2 * 0.5 * 1 / 1.5, 3)

    def test_both_empty_agree(self):
        assert box_f1([], []) == 1.0
