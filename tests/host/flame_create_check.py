"""Dry run of the Flame clip creator's naming, nothing is created.

Run it in Flame's Python console (Shift+F2 > Python) with AYON running
(`ayon_flame`, `ayon_core` and `ayon_editorial` importable):

    exec(open("/path/to/tests/host/flame_create_check.py").read())

Select the segments in the timeline first (none selected: all segments of
the current sequence). The script reads them into `ClipInfo`, takes the
`flame` profile of `project_settings["editorial"]["create"]
["CreateShotClip"]` (the editorial defaults when the project has none),
runs the shot solver with those values as the pre-create data, and prints
per clip: newClipName, folderPath, productName, heroTrack, parents.

It renames nothing, creates no instance and writes no marker. Change the
settings below to try other pre-create values (any key of the profile).
"""
from ayon_core.pipeline.context_tools import get_current_project_settings

# --- settings ---------------------------------------------------------------
HERO_TRACK = ""  # driving track name for vertical sync (needs vSyncOn)
OVERRIDES = {}  # e.g. {"clipRename": True, "vSyncOn": True}
# ----------------------------------------------------------------------------


def run():
    import ayon_flame.api as ayfapi
    from ayon_editorial.shots.hierarchy import ShotHierarchySolver
    from ayon_editorial.shots.options import get_clip_creator_presets
    from ayon_editorial.shots.vertical_sync import VerticalSync

    selection = ayfapi.CTX.selection or []
    sequence = ayfapi.get_current_sequence(selection)
    if sequence is None:
        print("No sequence: select a sequence or some of its segments.")
        return None

    settings = get_current_project_settings()
    presets = get_clip_creator_presets(
        settings.get("editorial") or {}, "flame"
    )
    options = dict(presets)
    options.update({
        "clipVariant": "<track_name>",
        "plate_product_type": (presets["plate_product_types"] or ["plate"])[0],
        "vSyncTrack": HERO_TRACK,
    })
    options.update(OVERRIDES)

    segments = ayfapi.get_sequence_segments(sequence, selected=True)
    if not segments:
        segments = ayfapi.get_sequence_segments(sequence)
    # hero track first, as the creator does
    hero = [s for s in segments if s.parent.name.get_value() in HERO_TRACK]
    segments = hero + [s for s in segments if s not in hero]

    names = [
        track.name.get_value()
        for version in sequence.versions
        for track in version.tracks
    ]
    solver = ShotHierarchySolver(
        options,
        sequence.name.get_value().replace(" ", "_"),
        names,
        VerticalSync(),
    )
    results = []
    for index, segment in enumerate(segments):
        clip = ayfapi.clip_info_from_segment(segment, sequence)
        try:
            solution = solver.solve(clip, index)
        except ValueError as exc:
            print(f"[{index}] {clip.name}: ERROR {exc}")
            continue
        if solution is None:
            print(f"[{index}] {clip.name}: skipped (reviewable source)")
            continue
        data = solution.data
        print(
            f"[{index}] {clip.name} track={clip.track_name}\n"
            f"    newClipName: {solution.new_clip_name}\n"
            f"    folderPath:  {data['folderPath']}\n"
            f"    productName: {data['productName']}\n"
            f"    heroTrack:   {data['heroTrack']}\n"
            f"    parents:     {data['parents']}"
        )
        results.append(solution)
    return results


RESULTS = run()
