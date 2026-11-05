"""Run the shared shot solver on the selected Hiero clips. Creates nothing.

Paste into Hiero's Script Editor and run, with AYON running (`ayon_hiero`
and `ayon_editorial` loaded), a sequence open and the clips selected in the
timeline.

Settings at the top:
    TASK_TYPE      task type for the profile match, e.g. "Compositing"; None
                   matches the profiles without task types.
    USE_PROFILE    True: values from the editorial profile of the current
                   project (`project_settings["editorial"]`), when it can be
                   read; False (or when it fails): the hiero defaults of
                   `ayon_editorial.shots.options.PROFILE_DEFAULTS`.
    OVERRIDES      pre-create values to set on top, e.g. {"vSyncOn": True,
                   "vSyncTrack": "Video 1"}.

Output, per selected clip (in the order the creator runs them: the vertical
sync track first): `newClipName`, `folderPath`, `productName`, `heroTrack`
and `parents`. A clip of a reviewable source track that is not the driving
layer prints `skipped`. Clips are not renamed and no tag is written.
"""
import hiero.core

from ayon_hiero.api import clip_info_from_track_item, lib
from ayon_editorial.shots.hierarchy import ShotHierarchySolver, sanitize_name
from ayon_editorial.shots.options import (
    CLIP_CREATOR_ATTRIBUTES,
    PROFILE_DEFAULTS,
    attribute_default,
    get_clip_creator_presets,
)
from ayon_editorial.shots.vertical_sync import VerticalSync

TASK_TYPE = None
USE_PROFILE = True
OVERRIDES = {}


def _presets():
    if USE_PROFILE:
        try:
            from ayon_core.pipeline import get_current_project_name
            from ayon_core.settings import get_project_settings

            settings = get_project_settings(get_current_project_name())
            presets = get_clip_creator_presets(
                settings.get("editorial") or {}, "hiero", TASK_TYPE
            )
            print("Profile: editorial settings")
            return presets
        except Exception as exc:  # noqa: BLE001
            print("Profile settings not readable ({}).".format(exc))
    print("Profile: hiero defaults")
    return dict(PROFILE_DEFAULTS)


def run():
    sequence = lib.get_current_sequence()
    items = [
        item for item in lib.get_timeline_selection()
        if isinstance(item, hiero.core.TrackItem)
    ]
    if sequence is None or not items:
        print("Select clips in the timeline first.")
        return

    presets = _presets()
    options = {
        spec.key: attribute_default(spec, presets)
        for spec in CLIP_CREATOR_ATTRIBUTES
        if spec.kind != "label"
    }
    options.update(OVERRIDES)

    track_names = [track.name() for track in sequence.videoTracks()]
    solver = ShotHierarchySolver(
        options, sanitize_name(sequence.name()), track_names, VerticalSync()
    )
    sync_track = options.get("vSyncTrack") or ""
    items.sort(key=lambda item: item.parent().name() not in sync_track)

    for index, item in enumerate(items):
        clip = clip_info_from_track_item(item, sequence)
        try:
            solution = solver.solve(clip, index)
        except ValueError as exc:
            print("{}: ERROR {}".format(clip.name, exc))
            continue
        if solution is None:
            print("{}: skipped".format(clip.name))
            continue
        data = solution.data
        print("{} ({} #{})".format(clip.name, clip.track_name, clip.index))
        print("  newClipName: {}".format(solution.new_clip_name))
        print("  folderPath:  {}".format(data.get("folderPath")))
        print("  productName: {}".format(data.get("productName")))
        print("  heroTrack:   {}".format(data.get("heroTrack")))
        print("  parents:     {}".format(data.get("parents")))


run()
