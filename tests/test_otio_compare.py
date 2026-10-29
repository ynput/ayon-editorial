"""Tests for `otio/compare.py` and its command line entry point."""
import copy
import json

import opentimelineio as otio
import pytest

from ayon_editorial.otio import compare

pytestmark = pytest.mark.otio


def _timeline(start=0.0, rate=24.0, metadata=None, name="sh010"):
    clip = otio.schema.Clip(
        name=name,
        source_range=otio.opentime.TimeRange(
            otio.opentime.RationalTime(start, rate),
            otio.opentime.RationalTime(10, rate),
        ),
        metadata=metadata or {},
    )
    track = otio.schema.Track(name="V1")
    track.append(clip)
    timeline = otio.schema.Timeline(name="tl")
    timeline.tracks.append(track)
    return timeline


def _write(path, timeline):
    otio.adapters.write_to_file(timeline, str(path))
    return str(path)


def test_compare_timelines_identical_no_differences():
    assert compare.compare_timelines(_timeline(), _timeline()) == []


def test_compare_timelines_zero_time_rate_ignored():
    left = _timeline(start=0.0, rate=24.0)
    right = _timeline(start=0.0, rate=25.0)
    # The source range start is zero on both; only the duration rate
    # differs, so make the duration equal too.
    for tl, rate in ((left, 24.0), (right, 25.0)):
        clip = tl.tracks[0][0]
        clip.source_range = otio.opentime.TimeRange(
            otio.opentime.RationalTime(0, rate),
            otio.opentime.RationalTime(0, rate),
        )
    assert compare.compare_timelines(left, right) == []


def test_compare_timelines_value_difference_reports_path():
    diffs = compare.compare_timelines(_timeline(start=1), _timeline(start=2))
    assert [d.kind for d in diffs] == ["changed"]
    assert diffs[0].path == (
        'tracks.children[0:Track "V1"].children[0:Clip "sh010"]'
        ".source_range.start_time.value"
    )


def test_compare_timelines_rate_difference_is_changed():
    diffs = compare.compare_timelines(
        _timeline(start=5, rate=23.976), _timeline(start=5, rate=23.976024)
    )
    assert any(d.path.endswith("start_time.rate") for d in diffs)


def test_compare_timelines_within_tolerance_equal():
    diffs = compare.compare_timelines(
        _timeline(start=1.0), _timeline(start=1.0 + 1e-9)
    )
    assert diffs == []


def test_compare_timelines_key_order_ignored():
    left = _timeline(metadata={"a": 1.5, "b": "x"})
    right = _timeline(metadata={"b": "x", "a": 1.5})
    assert compare.compare_timelines(left, right) == []


def test_compare_timelines_missing_and_added_keys():
    left = _timeline(metadata={"a": "x"})
    right = _timeline(metadata={"b": "x"})
    kinds = sorted(d.kind for d in compare.compare_timelines(left, right))
    assert kinds == ["added", "missing"]


def test_compare_timelines_int_vs_float_is_type_difference():
    diffs = compare.compare_timelines(
        _timeline(metadata={"n": 1}), _timeline(metadata={"n": 1.0})
    )
    assert [d.kind for d in diffs] == ["type"]


def test_compare_timelines_int_vs_float_loose_numbers_equal():
    options = compare.CompareOptions(loose_numbers=True)
    diffs = compare.compare_timelines(
        _timeline(metadata={"n": 1}), _timeline(metadata={"n": 1.0}), options
    )
    assert diffs == []


def test_compare_timelines_bool_is_not_a_number():
    diffs = compare.compare_timelines(
        _timeline(metadata={"n": True}), _timeline(metadata={"n": 1}),
        compare.CompareOptions(loose_numbers=True),
    )
    assert [d.kind for d in diffs] == ["type"]


def test_compare_timelines_ignore_glob_skips_path():
    options = compare.CompareOptions(ignore=("*.metadata.Date Modified",))
    diffs = compare.compare_timelines(
        _timeline(metadata={"Date Modified": "a", "k": 1}),
        _timeline(metadata={"Date Modified": "b", "k": 1}),
        options,
    )
    assert diffs == []


def test_compare_timelines_max_differences_stops_early():
    options = compare.CompareOptions(max_differences=1)
    diffs = compare.compare_timelines(
        _timeline(metadata={"a": 1, "b": 1}),
        _timeline(metadata={"a": 2, "b": 2}),
        options,
    )
    assert len(diffs) == 1


def test_compare_timelines_list_order_matters():
    left = _timeline()
    right = _timeline()
    for tl, names in ((left, "ab"), (right, "ba")):
        for name in names:
            tl.tracks[0].append(otio.schema.Gap(name=name))
    assert compare.compare_timelines(left, right)


def test_compare_timelines_clip_schema_versions_equal():
    data = json.loads(
        otio.adapters.write_to_string(_timeline(), "otio_json")
    )
    clip = data["tracks"]["children"][0]["children"][0]
    if clip["OTIO_SCHEMA"] != "Clip.2":
        pytest.skip("installed OTIO writes Clip.1 only")
    old = copy.deepcopy(data)
    old_clip = old["tracks"]["children"][0]["children"][0]
    old_clip["OTIO_SCHEMA"] = "Clip.1"
    old_clip["media_reference"] = old_clip.pop("media_references")[
        old_clip.pop("active_media_reference_key")
    ]
    left = otio.adapters.read_from_string(json.dumps(data), "otio_json")
    right = otio.adapters.read_from_string(json.dumps(old), "otio_json")
    assert compare.compare_timelines(left, right) == []


def test_format_differences_lists_lines_and_count():
    diffs = [compare.Difference("a.b", "changed", 1, 2)]
    assert compare.format_differences(diffs) == (
        "a.b: changed 1 != 2\n1 difference"
    )


def test_main_equal_files_exit_0(tmp_path, capsys):
    left = _write(tmp_path / "l.otio", _timeline())
    right = _write(tmp_path / "r.otio", _timeline())
    assert compare.main([left, right]) == 0
    assert capsys.readouterr().out == ""


def test_main_different_files_exit_1(tmp_path, capsys):
    left = _write(tmp_path / "l.otio", _timeline(start=1))
    right = _write(tmp_path / "r.otio", _timeline(start=2))
    assert compare.main([left, right]) == 1
    assert "1 difference" in capsys.readouterr().out


def test_main_json_output_is_list(tmp_path, capsys):
    left = _write(tmp_path / "l.otio", _timeline(start=1))
    right = _write(tmp_path / "r.otio", _timeline(start=2))
    assert compare.main([left, right, "--json"]) == 1
    assert json.loads(capsys.readouterr().out)[0]["kind"] == "changed"


def test_main_ignore_option_exit_0(tmp_path):
    left = _write(tmp_path / "l.otio", _timeline(metadata={"d": 1}))
    right = _write(tmp_path / "r.otio", _timeline(metadata={"d": 2}))
    assert compare.main([left, right, "--ignore", "*.metadata.d"]) == 0


def test_main_unreadable_file_exit_2(tmp_path):
    left = _write(tmp_path / "l.otio", _timeline())
    assert compare.main([left, str(tmp_path / "missing.otio")]) == 2


def test_main_usage_error_exit_2():
    assert compare.main(["only-one"]) == 2
