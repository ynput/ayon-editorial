"""`shots/instances.py`: sub-instance data per host loop."""
import copy

import pytest

from ayon_editorial.shots.clip import ClipInfo
from ayon_editorial.shots.instances import (
    build_clip_instances,
    link_parent_instance,
    shot_label,
)

IDS = {"shot": "x.shot", "plate": "x.plate", "audio": "x.audio"}


def _clip(**kwargs):
    params = dict(
        uid="clip-1", name="c1", index=1, track_name="V1", track_index=1,
        sequence_name="seq", timeline_in=100, timeline_out=148,
        source_in=10.0, source_out=58.0,
    )
    params.update(kwargs)
    return ClipInfo(**params)


def _solution(**kwargs):
    data = {
        "folderPath": "/shots/sq01/sh010",
        "folderName": "sh010",
        "hierarchy": "shots/sq01",
        "productName": "plateMain",
        "productType": "plate",
        "productBaseType": "plate",
        "variant": "main",
        "heroTrack": True,
        "workfileFrameStart": 1001,
        "handleStart": 10,
        "handleEnd": 12,
        "sourceResolution": False,
    }
    data.update(kwargs)
    return data


def _pre(**kwargs):
    data = {"export_audio": False}
    data.update(kwargs)
    return data


def test_hero_clip_makes_shot_and_plate_in_order():
    result = build_clip_instances(_solution(), _clip(), _pre(), IDS)
    assert list(result) == ["x.shot", "x.plate"]


def test_non_hero_clip_makes_plate_only():
    result = build_clip_instances(
        _solution(heroTrack=False), _clip(), _pre(export_audio=True), IDS)
    assert list(result) == ["x.plate"]


def test_audio_needs_hero_and_export_audio():
    hero = build_clip_instances(
        _solution(), _clip(), _pre(export_audio=True), IDS)
    assert list(hero) == ["x.shot", "x.plate", "x.audio"]
    no_audio = build_clip_instances(_solution(), _clip(), _pre(), IDS)
    assert "x.audio" not in no_audio


def test_shot_data_shot_hiero_and_flame_common():
    shot = build_clip_instances(_solution(), _clip(), _pre(), IDS)["x.shot"]
    assert shot["variant"] == "main"
    assert shot["productType"] == "shot"
    assert shot["productBaseType"] == "shot"
    assert shot["productName"] == "shotMain"
    assert shot["label"] == "/shots/sq01/sh010 shotMain"
    assert shot["clip_index"] == "clip-1"
    assert shot["task"] is None


def test_shot_creator_attributes_from_clip():
    attrs = build_clip_instances(
        _solution(), _clip(), _pre(), IDS)["x.shot"]["creator_attributes"]
    assert attrs["workfileFrameStart"] == 1001
    assert attrs["handleStart"] == 10 and attrs["handleEnd"] == 12
    assert attrs["frameStart"] == 1001
    # Both hosts: frameEnd = start + duration (49 frames).
    assert attrs["frameEnd"] == 1001 + 49
    assert attrs["clipIn"] == 100 and attrs["clipOut"] == 148
    assert attrs["clipDuration"] == 49
    assert attrs["sourceIn"] == 10 and attrs["sourceOut"] == 58
    assert isinstance(attrs["sourceIn"], int)
    assert attrs["useSourceResolution"] is False


def test_shot_source_resolution_flag():
    attrs = build_clip_instances(
        _solution(sourceResolution=True), _clip(), _pre(),
        IDS)["x.shot"]["creator_attributes"]
    assert attrs["useSourceResolution"] is True


def test_shot_retime_flags_flame_from_pre_create():
    pre = _pre(
        includeHandles=True, retimedHandles=False, retimedFramerange=False)
    attrs = build_clip_instances(
        _solution(), _clip(), pre, IDS)["x.shot"]["creator_attributes"]
    assert attrs["includeHandles"] is True
    assert attrs["retimedHandles"] is False
    assert attrs["retimedFramerange"] is False


def test_shot_retime_flags_hiero_gets_defaults():
    attrs = build_clip_instances(
        _solution(), _clip(), _pre(), IDS)["x.shot"]["creator_attributes"]
    assert attrs["includeHandles"] is False
    assert attrs["retimedHandles"] is True
    assert attrs["retimedFramerange"] is True


def test_plate_hiero_product_type_from_pre_create():
    plate = build_clip_instances(
        _solution(), _clip(), _pre(plate_product_type="reference"),
        IDS)["x.plate"]
    assert plate["productType"] == "reference"
    assert plate["productBaseType"] == "plate"
    assert plate["productName"] == "plateMain"
    assert plate["label"] == "/shots/sq01/sh010 plateMain"


def test_plate_product_type_default_plate():
    plate = build_clip_instances(
        _solution(), _clip(), _pre(), IDS)["x.plate"]
    assert plate["productType"] == "plate"


def test_plate_review_from_reviewable_source():
    plate = build_clip_instances(
        _solution(reviewableSource="clip_media"), _clip(), _pre(),
        IDS)["x.plate"]
    assert plate["creator_attributes"] == {
        "review": True, "reviewableSource": "clip_media"}
    plain = build_clip_instances(
        _solution(), _clip(), _pre(), IDS)["x.plate"]
    assert "review" not in plain["creator_attributes"]


def test_audio_data():
    audio = build_clip_instances(
        _solution(reviewableSource="V2"), _clip(),
        _pre(export_audio=True), IDS)["x.audio"]
    assert audio["variant"] == "main"
    assert audio["productType"] == "audio"
    assert audio["productBaseType"] == "audio"
    assert audio["productName"] == "audioMain"
    assert audio["label"] == "/shots/sq01/sh010 audioMain"
    assert audio["creator_attributes"] == {"review": True}


def test_audio_without_review():
    audio = build_clip_instances(
        _solution(), _clip(), _pre(export_audio=True), IDS)["x.audio"]
    assert audio["creator_attributes"] == {}


def test_sub_instances_do_not_share_data():
    result = build_clip_instances(
        _solution(), _clip(), _pre(export_audio=True), IDS)
    result["x.plate"]["creator_attributes"]["x"] = 1
    assert "x" not in result["x.audio"]["creator_attributes"]
    assert "x" not in result["x.shot"]["creator_attributes"]


def test_inputs_not_changed():
    solution = _solution(reviewableSource="clip_media")
    pre = _pre(export_audio=True)
    before = (copy.deepcopy(solution), copy.deepcopy(pre))
    build_clip_instances(solution, _clip(), pre, IDS)
    assert (solution, pre) == before


def test_solution_keys_are_copied_into_every_instance():
    solution = _solution(parents=[{"folder_name": "shots"}], hierarchyData={
        "folder": "shots"})
    result = build_clip_instances(
        solution, _clip(), _pre(export_audio=True), IDS)
    for data in result.values():
        assert data["parents"] == [{"folder_name": "shots"}]
        assert data["hierarchyData"] == {"folder": "shots"}
        assert data["folderPath"] == "/shots/sq01/sh010"


def test_link_parent_instance():
    plate = build_clip_instances(_solution(), _clip(), _pre(), IDS)["x.plate"]
    assert "parent_instance_id" not in plate
    link_parent_instance(
        plate, {"instance_id": "abc", "label": shot_label(_solution())})
    assert plate["parent_instance_id"] == "abc"
    assert plate["creator_attributes"]["parentInstance"] == (
        "/shots/sq01/sh010 shotMain")


def test_missing_hero_track_defaults_to_not_hero():
    solution = _solution()
    del solution["heroTrack"]
    assert list(build_clip_instances(
        solution, _clip(), _pre(), IDS)) == ["x.plate"]


def test_missing_folder_path_raises():
    solution = _solution()
    del solution["folderPath"]
    with pytest.raises(KeyError):
        build_clip_instances(solution, _clip(), _pre(), IDS)
