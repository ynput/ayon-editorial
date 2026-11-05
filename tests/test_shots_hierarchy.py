"""Tests of `shots/hierarchy.py`.

`test_*_hiero_*` / `test_*_flame_*` record what the host `PublishClip` /
`PublishableClip` produce today; `test_*_fix_*` test a deliberate change.
"""
from __future__ import annotations

import pytest

from ayon_editorial.shots.clip import ClipInfo
from ayon_editorial.shots.hierarchy import (
    ShotHierarchySolver,
    sanitize_name,
)

# host creator defaults
BASE = {
    "hierarchy": "{folder}/{sequence}/{track}", "clipRename": True,
    "clipName": "{track}{sequence}{shot}", "folder": "shots",
    "episode": "ep01", "sequence": "sq01", "track": "{_track_}",
    "shot": "sh###", "countFrom": 10, "countSteps": 10,
    "vSyncOn": False, "vSyncTrack": "", "clipVariant": "<track_name>",
    "plate_product_type": "plate", "workfileFrameStart": 1001,
    "handleStart": 10, "handleEnd": 10, "sourceResolution": False,
    "export_audio": False,
}


def clip(**kw):
    values = dict(
        uid="g1", name="my clip.01", index=5, track_name="Video 1",
        track_index=1, sequence_name="My Seq", timeline_in=100,
        timeline_out=200, source_in=0, source_out=100)
    values.update(kw)
    return ClipInfo(**values)


def solve(options=None, c=None, idx=0, seq="My Seq", tracks=()):
    """Solve as the Hiero reader does: names sanitised by the host."""
    opts = dict(BASE)
    opts.update(options or {})
    c = c or clip()
    c.name = sanitize_name(c.name)
    solver = ShotHierarchySolver(opts, sanitize_name(seq), tracks)
    return solver.solve(c, idx)


def test_solve_hiero_rename_names_and_hierarchy():
    sol = solve()
    d = sol.data
    assert sol.new_clip_name == "Video_1sq01sh010"
    assert "newClipName" not in d
    assert d["hierarchy"] == "shots/sq01/Video_1"
    assert d["folderName"] == "Video_1sq01sh010"
    assert d["folderPath"] == "/shots/sq01/Video_1/Video_1sq01sh010"
    assert d["hierarchyData"] == {
        "folder": "shots", "episode": "ep01", "sequence": "sq01",
        "track": "Video_1"}
    assert d["parents"] == [
        {"entity_type": "folder", "folder_type": "folder",
         "entity_name": "shots"},
        {"entity_type": "sequence", "folder_type": "sequence",
         "entity_name": "sq01"},
        {"entity_type": "sequence", "folder_type": "sequence",
         "entity_name": "Video_1"},
    ]
    assert d["productName"] == "plateVideo_1"
    assert d["productType"] == "plate"
    assert d["productBaseType"] == "plate"
    assert d["variant"] == "Video_1"
    assert d["heroTrack"] is True
    assert d["shot"] == "sh010"
    assert d["uuid"]


def test_solve_hiero_rename_index_steps_the_counter():
    assert solve(idx=0).new_clip_name.endswith("sh010")
    assert solve(idx=3).new_clip_name.endswith("sh040")


def test_solve_hiero_no_rename_keeps_clip_name():
    sol = solve({"clipRename": False})
    d = sol.data
    assert sol.new_clip_name is None
    assert d["folderName"] == "my_clip_01"
    assert d["hierarchyData"]["shot"] == "my_clip_01"
    assert d["folderPath"] == "/shots/sq01/Video_1/my_clip_01"


def test_solve_hiero_sequence_name_sanitized():
    sol = solve({"sequence": "{_sequence_}"}, seq="My Seq-v2")
    assert sol.data["hierarchy"] == "shots/My_Seq_v2/Video_1"


def test_solve_hiero_product_name_from_type_and_variant():
    d = solve({"plate_product_type": "render", "clipVariant": "bg"}).data
    assert d["productName"] == "renderBg"
    assert d["productType"] == "render"
    assert d["productBaseType"] == "plate"
    assert d["variant"] == "bg"


def test_solve_flame_track_name_noname_star():
    d = solve(c=clip(track_name="*", track_index=3)).data
    assert d["variant"] == "noname3"


def test_solve_flame_use_shot_name():
    c = clip(shot_name="ab_0010")
    sol = solve({"useShotName": True}, c)
    assert sol.new_clip_name is None
    assert sol.data["folderName"] == "ab_0010"
    assert sol.data["folderPath"] == "/shots/sq01/Video_1/ab_0010"
    assert sol.data["hierarchyData"]["shot"] == "ab_0010"


def test_solve_flame_use_shot_name_empty_raises():
    with pytest.raises(ValueError, match="Shot name"):
        solve({"useShotName": True}, clip(shot_name=""))


def test_solve_use_shot_name_ignored_without_clip_shot_name():
    sol = solve({"useShotName": True}, clip(shot_name=None))
    assert sol.new_clip_name == "Video_1sq01sh010"


def test_solve_flame_segment_index_counter():
    c = clip(shot_name="x", index=7)
    sol = solve({"segmentIndex": True}, c, idx=4)
    # steps * segment index, not stepped by the rename index
    assert sol.new_clip_name == "Video_1sq01sh070"


def test_solve_segment_index_ignored_without_clip_shot_name():
    sol = solve({"segmentIndex": True}, clip(shot_name=None), idx=4)
    assert sol.new_clip_name == "Video_1sq01sh050"


def test_solve_hash_padding():
    sol = solve({"shot": "sh####", "countFrom": 5})
    assert sol.new_clip_name == "Video_1sq01sh0005"


def test_solve_data_copies_pre_create_keys():
    d = solve({"includeHandles": True, "retimedHandles": False,
               "retimedFramerange": False, "export_audio": True,
               "sourceResolution": True}).data
    assert d["workfileFrameStart"] == 1001
    assert d["handleStart"] == 10 and d["handleEnd"] == 10
    assert d["includeHandles"] is True
    assert d["export_audio"] is True
    assert d["sourceResolution"] is True
    assert d["retimedHandles"] is False
    assert d["retimedFramerange"] is False


# review

def test_solve_hiero_review_source_hero():
    d = solve({"reviewableSource": "Video_2"}, clip(track_name="Video 1")
              ).data
    assert d["review"] is True
    assert d["reviewableSource"] == "Video_2"
    # set by the plate collector at publish, not stored by the creator
    assert "reviewTrack" not in d


def test_solve_hiero_review_track_not_driving_layer_skipped():
    opts = {"reviewableSource": "Video_2", "vSyncOn": True,
            "vSyncTrack": "Video 1"}
    assert solve(opts, clip(track_name="Video 2", track_index=2)) is None
    assert solve(opts, clip(track_name="Video 1")) is not None


def test_solve_hiero_review_follower_has_no_review_keys():
    solver = ShotHierarchySolver(
        dict(BASE, vSyncOn=True, vSyncTrack="Video 1",
             reviewableSource="Video_3"), "seq")
    solver.solve(clip(), 0)
    d = solver.solve(clip(track_name="Video 2", track_index=2,
                          timeline_in=120, timeline_out=150), 1).data
    assert "review" not in d and "reviewableSource" not in d
    assert "reviewTrack" not in d


def test_solve_hiero_review_regex_resolves_track():
    d = solve({"reviewableSource": "review_track_regex_pattern",
               "reviewTrackRegexPattern": "^<track_name>_review$"},
              tracks=["Video 1", "Video 1_review", "Video 2"],
              c=clip(track_name="Video 1")).data
    assert d["reviewableSource"] == "Video 1_review"
    assert "reviewTrackRegexPattern" not in d
    assert "review" not in d


def test_solve_hiero_review_regex_invalid_or_unmatched_is_none():
    for pattern in ("(", "zzz"):
        d = solve({"reviewableSource": "review_track_regex_pattern",
                   "reviewTrackRegexPattern": pattern},
                  tracks=["Video 1"]).data
        assert d["reviewableSource"] is None


# fixes

def test_solve_fix_count_from_zero_is_kept():
    # was `countFrom or 10`
    assert solve({"countFrom": 0}).new_clip_name.endswith("sh000")
    assert solve({"countFrom": 0, "countSteps": 0}, idx=3
                 ).new_clip_name.endswith("sh000")


def test_solve_fix_none_counts_take_defaults():
    sol = solve({"countFrom": None, "countSteps": None}, idx=1)
    assert sol.new_clip_name.endswith("sh020")


def test_solve_fix_retimed_false_not_replaced_by_default():
    d = solve({"retimedHandles": False}).data
    assert d["retimedHandles"] is False


def test_solve_fix_export_audio_copied():
    # Hiero's tag key was `audio`, never in the pre-create data
    assert solve({"export_audio": True}).data["export_audio"] is True
    assert "audio" not in solve().data


def test_solve_fix_empty_hierarchy_token_takes_default():
    # was KeyError in Hiero (`track_item_default_data["folder"]`)
    opts = {"folder": "", "sequence": None}
    sol = solve(opts)
    assert sol.data["hierarchy"] == "shots/My_Seq/Video_1"


def test_solve_fix_all_defaults_do_not_raise():
    solver = ShotHierarchySolver({}, sanitize_name("My Seq"))
    sol = solver.solve(clip(), 0)
    assert sol.new_clip_name is None
    assert sol.data["hierarchy"] == "shots/My_Seq/Video_1"
    assert sol.data["parents"][0]["entity_name"] == "shots"
    renamed = ShotHierarchySolver({"clipRename": True}, "s").solve(
        clip(index=7, track_index=2), 0)
    assert renamed.new_clip_name == "shot_002_0007"


def test_solve_fix_hash_in_other_tokens_is_the_counter():
    sol = solve({"episode": "ep##", "hierarchy": "{folder}/{episode}",
                 "clipName": "{episode}"})
    assert sol.new_clip_name == "ep10"


def test_solve_fix_review_track_old_key_is_reviewable_source():
    d = solve({"reviewTrack": "Video_2"}).data
    assert d["reviewableSource"] == "Video_2"
    assert d["review"] is True


def test_solve_unknown_token_names_the_token():
    with pytest.raises(ValueError, match="nope"):
        solve({"clipName": "{nope}"})


def test_solve_unknown_folder_type_raises():
    with pytest.raises(ValueError, match="folder type"):
        solve({"hierarchy": "{folder}/{_clip_}"})


def test_solve_literal_hierarchy_segment_is_a_folder():
    sol = solve({"hierarchy": "shots/{sequence}"})
    assert sol.data["parents"][0] == {
        "entity_type": "folder", "folder_type": "folder",
        "entity_name": "shots"}


def test_solve_keeps_names_as_the_host_gives_them():
    """Flame keeps clip names raw and only replaces spaces in the
    sequence name: the solver does not sanitise on its own."""
    solver = ShotHierarchySolver(
        dict(BASE, clipRename=False, sequence="{_sequence_}"), "Seq-01")
    sol = solver.solve(clip(name="A010-B.v1"), 0)
    assert sol.data["folderName"] == "A010-B.v1"
    assert sol.data["hierarchy"] == "shots/Seq-01/Video_1"


def test_solve_review_skip_needs_the_exact_track():
    """A track whose name is only part of the reviewable source is kept."""
    opts = {"reviewableSource": "clip_media", "vSyncOn": True,
            "vSyncTrack": "Video 1"}
    assert solve(opts, clip(track_name="media", track_index=2)) is not None


def test_solve_unknown_positional_token_is_a_value_error():
    with pytest.raises(ValueError):
        solve({"clipName": "{}"}, idx=0)
