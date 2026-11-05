"""Tests of `shots/vertical_sync.py` and its use by the shot solver.

Characterization of the Hiero (`vertical_clip_match` / `_used`) and Flame
(`PublishableClip` class dicts) vertical sync, and of the deliberate
differences listed in the module docstring of `hierarchy.py`.
"""
from __future__ import annotations

from ayon_editorial.shots.clip import ClipInfo
from ayon_editorial.shots.hierarchy import ShotHierarchySolver
from ayon_editorial.shots.vertical_sync import VerticalSync

HERO = {
    "productName": "plateMain",
    "variant": "main",
    "newClipName": "sh010",
    "heroTrack": True,
    "hierarchy": "shots/sq01",
}


def _sync() -> VerticalSync:
    sync = VerticalSync()
    sync.register_hero(100, 200, HERO)
    return sync


def _distribute(sync, name="plateV1", variant="v1", track=2, idx=1,
                tin=120, tout=150):
    return sync.distribute(tin, tout, name, variant, track, idx)


def test_distribute_no_hero_range_none():
    assert _distribute(_sync(), tin=90, tout=150) is None
    assert _distribute(_sync(), tin=120, tout=250) is None
    assert _distribute(VerticalSync()) is None


def test_distribute_copies_hero_data_and_unsets_hero_track():
    sync = _sync()
    data = _distribute(sync)
    assert data["heroTrack"] is False
    assert data["newClipName"] == "sh010"
    assert data["hierarchy"] == "shots/sq01"
    assert data["productName"] == "plateV1"
    assert data["variant"] == "v1"
    # the stored hero is untouched
    assert sync.hero_clips[(100, 200)]["heroTrack"] is True


def test_distribute_product_name_same_as_hero_gets_track_index_hiero():
    data = _distribute(_sync(), name="plateMain", variant="main", track=3)
    assert data["productName"] == "plateMain3"
    assert data["variant"] == "main3"


def test_distribute_used_name_gets_rename_index_hiero():
    sync = _sync()
    assert _distribute(sync, idx=1)["productName"] == "plateV1"
    second = _distribute(sync, idx=2)
    assert second["productName"] == "plateV12"
    assert second["variant"] == "v12"


def test_distribute_used_name_second_collision_flame_fallback():
    sync = _sync()
    names = [_distribute(sync, track=2, idx=2)["productName"]
             for _ in range(4)]
    # plateV1, plateV12, plateV122 (track+rename), plateV12_3 (counter)
    assert names == ["plateV1", "plateV12", "plateV122", "plateV12_3"]
    assert len(set(names)) == 4


def test_distribute_substring_name_is_not_a_hero_match():
    # Flame used `in`; the shared code compares for equality (Hiero)
    sync = VerticalSync()
    sync.register_hero(0, 10, dict(HERO, productName="plateMainX"))
    data = sync.distribute(1, 5, "plateMain", "main", 2, 1)
    assert data["productName"] == "plateMain"


def test_first_containing_hero_wins_and_same_range_replaces():
    sync = VerticalSync()
    sync.register_hero(0, 100, dict(HERO, newClipName="a"))
    sync.register_hero(10, 50, dict(HERO, newClipName="b"))
    assert sync.find_hero(20, 30)["newClipName"] == "a"
    sync.register_hero(0, 100, dict(HERO, newClipName="c"))
    assert list(sync.hero_clips) == [(0, 100), (10, 50)]
    assert sync.find_hero(20, 30)["newClipName"] == "c"


def test_used_names_are_per_hero_clip_name_and_product():
    sync = VerticalSync()
    sync.register_hero(0, 10, dict(HERO, newClipName="a"))
    sync.register_hero(20, 30, dict(HERO, newClipName="b"))
    assert sync.distribute(1, 2, "plateV1", "v1", 2, 1)["productName"] == \
        "plateV1"
    assert sync.distribute(21, 22, "plateV1", "v1", 2, 2)["productName"] == \
        "plateV1"


def test_reset_clears_state():
    sync = _sync()
    _distribute(sync)
    sync.reset()
    assert sync.hero_clips == {} and sync.used_names == {}
    assert _distribute(sync) is None


# solver integration

def _clip(uid, track, track_index, tin=100, tout=200, index=1):
    return ClipInfo(
        uid=uid, name=f"clip{uid}", index=index, track_name=track,
        track_index=track_index, sequence_name="seq", timeline_in=tin,
        timeline_out=tout, source_in=0, source_out=100)


OPTIONS = {
    "hierarchy": "{folder}/{sequence}/{track}", "clipRename": True,
    "clipName": "{sequence}{shot}", "folder": "shots", "episode": "ep01",
    "sequence": "sq01", "track": "{_track_}", "shot": "sh###",
    "countFrom": 10, "countSteps": 10, "vSyncOn": True,
    "vSyncTrack": "Video 1", "clipVariant": "<track_name>",
}


def test_solver_vertical_sync_follower_inherits_hero_hiero():
    solver = ShotHierarchySolver(OPTIONS, "seq")
    hero = solver.solve(_clip("a", "Video 1", 1), 0)
    follower = solver.solve(_clip("b", "Video 2", 2, 120, 150), 1)
    assert hero.data["heroTrack"] is True
    assert hero.data["productName"] == "plateVideo_1"
    assert follower.data["heroTrack"] is False
    assert follower.new_clip_name == hero.new_clip_name == "sq01sh010"
    assert follower.data["hierarchy"] == hero.data["hierarchy"]
    assert follower.data["productName"] == "plateVideo_2"
    assert follower.data["variant"] == "Video_2"


def test_solver_follower_outside_hero_range_keeps_own_data():
    solver = ShotHierarchySolver(OPTIONS, "seq")
    solver.solve(_clip("a", "Video 1", 1), 0)
    other = solver.solve(_clip("b", "Video 2", 2, 300, 400), 1)
    assert other.data["heroTrack"] is True
    assert other.new_clip_name == "sq01sh020"


def test_solver_two_followers_same_variant_get_unique_names():
    options = dict(OPTIONS, clipVariant="main")
    solver = ShotHierarchySolver(options, "seq")
    solver.solve(_clip("a", "Video 1", 1), 0)
    one = solver.solve(_clip("b", "Video 2", 2, 120, 150), 1)
    two = solver.solve(_clip("c", "Video 3", 3, 120, 150), 2)
    # hero is plateMain: followers get the track index, then rename index
    assert one.data["productName"] == "plateMain2"
    assert two.data["productName"] == "plateMain3"


def test_solver_shared_state_between_solvers_and_reset():
    sync = VerticalSync()
    ShotHierarchySolver(OPTIONS, "seq", vertical_sync=sync).solve(
        _clip("a", "Video 1", 1), 0)
    assert (100, 200) in sync.hero_clips
    sync.reset()
    assert not sync.hero_clips
