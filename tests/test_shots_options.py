"""`shots/options.py`: schema, profile lookup, hidden values."""
import ast
from pathlib import Path

import pytest

from ayon_editorial.shots import options
from ayon_editorial.shots.options import (
    ALL_OVERRIDES,
    CLIP_CREATOR_ATTRIBUTES,
    PROFILE_DEFAULTS,
    SHOT_INSTANCE_ATTRIBUTES,
    attribute_default,
    attribute_items,
    fill_hidden_values,
    filter_profiles,
    get_clip_creator_presets,
    get_hidden_attributes,
    supported_attribute_keys,
)

SERVER = (
    Path(__file__).resolve().parent.parent
    / "server" / "settings" / "create_plugins.py"
)


def _spec(key):
    return next(s for s in CLIP_CREATOR_ATTRIBUTES if s.key == key)


def _settings(*profiles):
    return {"create": {"CreateShotClip": {"profiles": list(profiles)}}}


# -- schema ------------------------------------------------------------

def test_schema_keys_unique():
    keys = [s.key for s in CLIP_CREATOR_ATTRIBUTES]
    assert len(keys) == len(set(keys))


def test_schema_is_union_of_both_hosts():
    hiero = supported_attribute_keys("hiero")
    flame = supported_attribute_keys("flame")
    assert {"useShotName", "segmentIndex"} <= flame - hiero
    assert "reviewTrackRegexPattern" in hiero - flame
    # Hiero gains the retime flags.
    assert {"includeHandles", "retimedHandles", "retimedFramerange"} <= hiero
    assert "use_selection" in hiero & flame


def test_section_labels_present():
    labels = [s.label for s in CLIP_CREATOR_ATTRIBUTES if s.kind == "label"]
    assert labels == [
        "Shot Hierarchy And Rename Settings",
        "Shot Template Keywords",
        "Vertical Synchronization Of Attributes",
        "Publish Settings",
        "Shot Attributes",
    ]


def test_shot_attributes_fps_fix():
    fps = next(s for s in SHOT_INSTANCE_ATTRIBUTES if s.key == "fps")
    values = [value for value, _label in fps.items]
    assert 23.976 in values and 23.997 not in values
    # Every label maps to its own value.
    assert all(
        str(value) == label for value, label in fps.items
        if value != "from_selection"
    )


def test_shot_attributes_union():
    keys = {s.key for s in SHOT_INSTANCE_ATTRIBUTES}
    assert {
        "fps", "workfileFrameStart", "handleStart", "handleEnd",
        "frameStart", "frameEnd", "clipIn", "clipOut", "clipDuration",
        "sourceIn", "sourceOut", "includeHandles", "retimedHandles",
        "retimedFramerange", "useSourceResolution",
    } == keys
    read_only = {s.key for s in SHOT_INSTANCE_ATTRIBUTES if s.disabled}
    assert read_only == {
        "frameStart", "frameEnd", "clipIn", "clipOut", "clipDuration",
        "sourceIn", "sourceOut",
    }


def test_defaults_come_from_presets():
    presets = dict(PROFILE_DEFAULTS, handleStart=5, sequence="a")
    assert attribute_default(_spec("handleStart"), presets) == 5
    assert attribute_default(_spec("sequence"), presets) == "a"
    assert attribute_default(_spec("use_selection"), presets) is True
    assert attribute_default(_spec("clipVariant"), presets) == "<track_name>"
    assert attribute_default(_spec("plate_product_type"), presets) == "plate"


def test_items_from_presets_and_tracks():
    presets = dict(
        PROFILE_DEFAULTS, clip_variants=["main", "bg"],
        plate_product_types=["plate", "reference"],
    )
    variants = attribute_items(_spec("clipVariant"), presets)
    assert [i["value"] for i in variants] == ["main", "bg"]
    types = attribute_items(_spec("plate_product_type"), presets)
    assert [i["value"] for i in types] == ["plate", "reference"]
    # Empty plate_product_types gives `plate`.
    types = attribute_items(_spec("plate_product_type"), PROFILE_DEFAULTS)
    assert [i["value"] for i in types] == ["plate"]


def test_items_track_names_and_host_items():
    spec = _spec("reviewableSource")
    hiero = attribute_items(spec, None, ["V1", "V2"], "hiero")
    assert [i["value"] for i in hiero] == [
        None, "clip_media", "review_track_regex_pattern", "V1", "V2"]
    assert hiero[-1]["label"] == "Track: V2"
    flame = attribute_items(spec, None, ["V1"], "flame")
    assert [i["value"] for i in flame] == [None, "clip_media", "V1"]


def test_vsync_track_without_tracks():
    items = attribute_items(_spec("vSyncTrack"), None, [])
    assert items == [{"value": None, "label": "<nothing to select>"}]


# -- profiles ----------------------------------------------------------

def test_filter_profiles_by_host():
    hiero = {"host_names": ["hiero"], "name": "h"}
    flame = {"host_names": ["flame"], "name": "f"}
    assert filter_profiles([hiero, flame], "flame")["name"] == "f"
    assert filter_profiles([hiero, flame], "hiero")["name"] == "h"
    assert filter_profiles([hiero, flame], "resolve") is None


def test_filter_profiles_empty_and_star_match_all():
    assert filter_profiles([{"name": "a"}], "hiero")["name"] == "a"
    assert filter_profiles(
        [{"host_names": ["*"], "name": "a"}], "hiero")["name"] == "a"
    assert filter_profiles([], "hiero") is None
    assert filter_profiles(None, "hiero") is None


def test_filter_profiles_most_specific_wins():
    generic = {"name": "generic"}
    host = {"host_names": ["hiero"], "name": "host"}
    both = {
        "host_names": ["hiero"], "task_types": ["Editing"], "name": "both"}
    profiles = [generic, host, both]
    assert filter_profiles(profiles, "hiero", "Editing")["name"] == "both"
    assert filter_profiles(profiles, "hiero", "Layout")["name"] == "host"
    assert filter_profiles(profiles, "hiero")["name"] == "host"
    assert filter_profiles(profiles, "flame", "Editing")["name"] == "generic"


def test_filter_profiles_task_filter_needs_a_task_type():
    profile = {"task_types": ["Editing"], "name": "t"}
    assert filter_profiles([profile], "hiero") is None
    assert filter_profiles([profile], "hiero", "Editing")["name"] == "t"


def test_filter_profiles_regex_fullmatch():
    profile = {"host_names": ["hie.*"], "name": "r"}
    assert filter_profiles([profile], "hiero")["name"] == "r"
    assert filter_profiles([{"host_names": ["hie"]}], "hiero") is None


def test_filter_profiles_tie_prefers_first_key_then_order():
    task_only = {"task_types": ["Editing"], "name": "task"}
    host_only = {"host_names": ["hiero"], "name": "host"}
    assert filter_profiles(
        [task_only, host_only], "hiero", "Editing")["name"] == "host"
    first = {"host_names": ["hiero"], "name": "first"}
    second = {"host_names": ["hiero"], "name": "second"}
    assert filter_profiles([first, second], "hiero")["name"] == "first"


def test_presets_matched_profile_over_defaults():
    settings = _settings(
        {"host_names": ["flame"], "handleStart": 5, "sequence": "a"},
        {"host_names": ["hiero"], "handleStart": 8},
    )
    presets = get_clip_creator_presets(settings, "flame")
    assert presets["handleStart"] == 5
    assert presets["sequence"] == "a"
    # A key the profile lacks comes from the defaults.
    assert presets["countFrom"] == PROFILE_DEFAULTS["countFrom"]


def test_presets_without_match_are_defaults():
    presets = get_clip_creator_presets(
        _settings({"host_names": ["flame"]}), "hiero")
    assert presets == PROFILE_DEFAULTS
    assert get_clip_creator_presets({}, "hiero") == PROFILE_DEFAULTS
    # The defaults are not shared.
    presets["overrides"].append("x")
    assert "x" not in PROFILE_DEFAULTS["overrides"]


def test_profile_defaults_match_server_model():
    tree = ast.parse(SERVER.read_text())
    model = next(
        n for n in tree.body
        if isinstance(n, ast.ClassDef) and n.name == "ClipCreatorProfile")
    checked = 0
    for node in model.body:
        if not (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.value, ast.Call)
            and node.value.args
            and isinstance(node.value.args[0], ast.Constant)
        ):
            continue
        key = node.target.id
        assert PROFILE_DEFAULTS[key] == node.value.args[0].value, key
        checked += 1
    assert checked >= 20
    assert tuple(PROFILE_DEFAULTS["overrides"]) == ALL_OVERRIDES


# -- hidden ------------------------------------------------------------

def test_hidden_all_overridable_shows_everything_supported():
    presets = dict(PROFILE_DEFAULTS)
    hidden = get_hidden_attributes(presets, supported_attribute_keys("flame"))
    # vSyncTrack is shown with vSyncOn overridable; Hiero-only key hidden.
    assert hidden == {"reviewTrackRegexPattern"}


def test_hidden_flame_rule_not_overridable_is_hidden():
    presets = dict(PROFILE_DEFAULTS, overrides=["hierarchy"])
    hidden = get_hidden_attributes(presets, supported_attribute_keys("flame"))
    assert "hierarchy" not in hidden
    assert {"clipName", "handleStart", "vSyncOn", "vSyncTrack"} <= hidden
    assert "use_selection" not in hidden


def test_hidden_vsync_track_follows_vsync_on():
    base = dict(PROFILE_DEFAULTS, overrides=["hierarchy"])
    supported = supported_attribute_keys("hiero")
    assert "vSyncTrack" in get_hidden_attributes(base, supported)
    on_in_profile = dict(base, vSyncOn=True)
    assert "vSyncTrack" not in get_hidden_attributes(on_in_profile, supported)
    overridable = dict(base, overrides=["vSyncOn"])
    assert "vSyncTrack" not in get_hidden_attributes(overridable, supported)


def test_hidden_unsupported_always_hidden():
    presets = dict(PROFILE_DEFAULTS)
    hidden = get_hidden_attributes(presets, supported_attribute_keys("hiero"))
    assert {"useShotName", "segmentIndex"} <= hidden
    # Even when the profile marks them overridable.
    assert "useShotName" in presets["overrides"]


def test_fill_hidden_values():
    presets = dict(
        PROFILE_DEFAULTS, handleStart=7, clip_variants=["main", "bg"],
        plate_product_types=["ref"],
    )
    data = {"handleStart": 99, "hierarchy": "x"}
    filled = fill_hidden_values(
        data, presets, {"handleStart", "clipVariant", "plate_product_type"})
    assert filled["handleStart"] == 7
    assert filled["hierarchy"] == "x"
    assert filled["clipVariant"] == "main"
    assert filled["plate_product_type"] == "ref"
    assert data["handleStart"] == 99  # input untouched


def test_fill_hidden_values_skips_keys_without_value():
    filled = fill_hidden_values({}, PROFILE_DEFAULTS, {"vSyncTrack"})
    assert "vSyncTrack" not in filled


def test_module_exports():
    for name in options.__all__:
        assert hasattr(options, name)


@pytest.mark.parametrize("host", ["hiero", "flame"])
def test_every_visible_spec_has_a_default_source(host):
    """A visible non-enum spec has a profile key or its own default."""
    for spec in CLIP_CREATOR_ATTRIBUTES:
        if spec.kind in ("label", "enum"):
            continue
        assert spec.key in PROFILE_DEFAULTS or spec.default is not None
