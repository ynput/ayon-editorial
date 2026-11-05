"""`shots/retime.py`: Flame characterization and the fixes."""
import pytest

from ayon_editorial.shots.retime import (
    RetimeOptions,
    handles_for_core,
    retime_instance_data,
    source_range_with_handles,
    unlinked_retime_values,
    workfile_frame_start,
)


def _core_scale(handle_start, handle_end, speed):
    """What ayon-core `get_media_range_with_retimes` does to handles."""
    start = handle_start * abs(speed)
    end = handle_end * abs(speed)
    if speed < 0:
        start, end = end, start
    return start, end


# -- options -----------------------------------------------------------

def test_options_defaults():
    assert RetimeOptions() == RetimeOptions(False, True, True)


def test_options_from_data():
    options = RetimeOptions.from_data({
        "includeHandles": True, "retimedHandles": False,
        "retimedFramerange": False,
    })
    assert options == RetimeOptions(True, False, False)


def test_options_from_data_older_workfile_keeps_defaults():
    assert RetimeOptions.from_data({}) == RetimeOptions()
    assert RetimeOptions.from_data(
        {"includeHandles": None, "retimedHandles": None}) == RetimeOptions()


def test_options_to_attributes():
    assert RetimeOptions(True, False, True).to_attributes() == {
        "includeHandles": True, "retimedHandles": False,
        "retimedFramerange": True,
    }


# -- workfile start ----------------------------------------------------

def test_workfile_frame_start_flame_include_handles():
    assert workfile_frame_start(1001, 10, True) == 1011


def test_workfile_frame_start_flame_exclude_handles():
    assert workfile_frame_start(1001, 10, False) == 1001


# -- handles for core --------------------------------------------------

def test_handles_for_core_retimed_pass_through():
    assert handles_for_core(10, 12, 2.0, True) == (10, 12)
    assert handles_for_core(10, 12, -0.5, True) == (10, 12)


def test_handles_for_core_not_retimed_core_result_equals_handles():
    for speed in (2.0, 0.5, 1.0, 0.25):
        given = handles_for_core(10, 12, speed, False)
        assert _core_scale(*given, speed) == (10, 12), speed


def test_handles_for_core_not_retimed_reverse():
    for speed in (-2.0, -0.5):
        given = handles_for_core(10, 12, speed, False)
        assert _core_scale(*given, speed) == (10, 12), speed


def test_handles_for_core_rounding_is_documented_bound():
    # 10 / 3 is not an integer: off by less than speed / 2.
    given = handles_for_core(10, 10, 3.0, False)
    start, end = _core_scale(*given, 3.0)
    assert abs(start - 10) <= 1.5 and abs(end - 10) <= 1.5
    assert all(isinstance(value, int) for value in given)


def test_handles_for_core_freeze_frame_unchanged():
    assert handles_for_core(10, 12, 0, False) == (10, 12)


# -- source range (port of Flame extract_product_resources) -------------

def _range(**kwargs):
    params = dict(
        frame_start=1001, handle_start=10, handle_end=10,
        source_start_handles=90, source_end_handles=210,
        retimed_speed=1.0, retimed_handle_start=10,
        retimed_handle_end=10, retimed_source_duration=101,
        include_handles=False, retimed_handles=True,
    )
    params.update(kwargs)
    return source_range_with_handles(**params)


def test_source_range_flame_not_retimed():
    result = _range()
    assert result.source_start_handles == 90
    assert result.source_end_handles == 210
    assert result.frame_start_handle == 991
    assert result.repre_frame_start == 991
    assert result.source_duration_handles == 121


def test_source_range_flame_not_retimed_include_handles():
    result = _range(include_handles=True)
    assert result.frame_start_handle == 1001
    assert result.repre_frame_start == 991


def test_source_range_flame_retimed_handles():
    # Speed 2: source 200 frames, handles 20 each.
    result = _range(
        retimed_speed=2.0, retimed_handle_start=20, retimed_handle_end=20,
        retimed_source_duration=200, source_start_handles=100,
    )
    assert result.source_start_handles == 80
    assert result.source_end_handles == 80 + 199 + 40
    assert result.source_duration_handles == 240
    assert result.frame_start_handle == 991


def test_source_range_flame_retimed_handles_include_handles():
    result = _range(
        retimed_speed=2.0, retimed_handle_start=20, retimed_handle_end=20,
        retimed_source_duration=200, source_start_handles=100,
        include_handles=True,
    )
    assert result.frame_start_handle == (1001 - 10) + 20
    assert result.repre_frame_start == 991


def test_source_range_flame_handles_not_retimed():
    result = _range(
        retimed_speed=2.0, retimed_handle_start=20, retimed_handle_end=20,
        retimed_source_duration=200, source_start_handles=100,
        retimed_handles=False,
    )
    assert result.source_start_handles == 100
    assert result.source_end_handles == 100 + 199 + 10 + 10
    result = _range(
        retimed_speed=2.0, retimed_source_duration=200,
        source_start_handles=100, retimed_handles=False,
        include_handles=True,
    )
    assert result.frame_start_handle == 1001


# -- unlinked media ----------------------------------------------------

def test_unlinked_no_speed_change():
    values = unlinked_retime_values(100, 199, 100, 5, 5)
    assert values["speed"] == 1.0
    assert values["source_duration"] == 100
    assert values["source_start_handles"] == 95


def test_unlinked_speed_from_durations():
    values = unlinked_retime_values(100, 299, 100, 5, 5)
    assert values["speed"] == 2.0
    assert values["handle_start"] == 10
    assert values["source_duration"] == 400


def test_unlinked_end_with_handles_fix():
    """Flame had `source_out - handle_end`; the end grows by the handle."""
    values = unlinked_retime_values(100, 199, 100, 5, 7)
    assert values["source_end_handles"] == 206


# -- instance data -----------------------------------------------------

def test_instance_data_shot_duration_only_when_retimed_framerange():
    on = retime_instance_data(RetimeOptions(retimed_framerange=True))
    assert on["shotDurationFromSource"] is True
    off = retime_instance_data(RetimeOptions(retimed_framerange=False))
    # ayon-core tests the key's presence, so a False value is not enough.
    assert "shotDurationFromSource" not in off
    assert off["retimedFramerange"] is False


@pytest.mark.parametrize("flag", [True, False])
def test_instance_data_flags(flag):
    data = retime_instance_data(RetimeOptions(flag, flag, flag))
    assert data["includeHandles"] is flag
    assert data["retimedHandles"] is flag


def test_from_data_missing_keys_take_given_defaults():
    """An older Hiero workfile has no retime keys: no retimed range."""
    legacy = RetimeOptions(retimed_framerange=False)
    options = RetimeOptions.from_data({}, defaults=legacy)
    assert options == legacy
    assert "shotDurationFromSource" not in retime_instance_data(options)
    set_on = RetimeOptions.from_data(
        {"retimedFramerange": True}, defaults=legacy
    )
    assert set_on.retimed_framerange is True
