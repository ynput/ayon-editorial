"""Compare the Hiero OTIO export with the reference exporter, in Hiero.

Paste this file into Hiero's Script Editor and run it, with AYON running
(the `ayon_hiero` and `ayon_editorial` addons loaded) and a sequence open
in the timeline. Nothing is written or published.

Setup (the two paths just below):
    EDITORIAL_REPO  checkout of ayon-editorial that holds
                    `tests/resources/host_exports/hiero_reference.py`
                    (the verbatim copy of the old host export).
    EDITORIAL_CLIENT  only when `import ayon_editorial` fails in Hiero:
                    the `client` folder of that checkout.

What it does: reads the active sequence into the plain input shape of
`hiero_input.json` (track items, media, tags, TimeWarp soft effects, the
animated knobs sampled per frame), runs the reference exporter on that, runs
the new `ayon_hiero.api.otio.hiero_export.create_otio_timeline()` on the
sequence itself, and compares both with
`ayon_editorial.otio.compare.compare_timelines`.

Output: `OK` when the two timelines are equal, else the list of
differences (path, left = reference, right = new export). A read the dump
cannot make (for example a soft effect without the TimeWarp knobs) is
printed as `DUMP WARNING` and left out of both sides.

Limit: the dump takes the framerate of a track item from its clip, as the
reference fixture does.
"""
import importlib.util
import os
import sys
import types

import hiero.core
import hiero.ui

EDITORIAL_REPO = "/path/to/ayon-editorial"
EDITORIAL_CLIENT = ""  # e.g. EDITORIAL_REPO + "/client", only when needed

PROJECT_KEYS = (
    "useOCIOEnvironmentOverride",
    "lutSetting16Bit",
    "lutSetting8Bit",
    "lutSettingFloat",
    "lutSettingLog",
    "lutSettingViewer",
    "lutSettingWorkingSpace",
    "lutUseOCIOForExport",
    "ocioConfigName",
    "ocioConfigPath",
)


def _flatten(items):
    for item in items:
        if isinstance(item, (list, tuple)):
            for sub in _flatten(item):
                yield sub
        else:
            yield item


def _rational(obj):
    num, den = obj.framerate().toRational()
    return [num, den]


def _tags(obj):
    return [
        {
            "name": tag.name(),
            "icon": tag.icon(),
            "visible": tag.visible(),
            "in_time": tag.inTime(),
            "metadata": dict(tag.metadata().dict()),
        }
        for tag in obj.tags()
    ]


def _knob(knob, first, last):
    data = {"value": knob.value()}
    if knob.isAnimated():
        data["curve"] = [
            [frame, knob.getValueAt(frame)]
            for frame in range(first, last + 1)
        ]
    return data


def _dump_clip(clip):
    media = clip.mediaSource()
    info = media.fileinfos().pop()
    return {
        "framerate": _rational(clip),
        "colour_transform": clip.sourceMediaColourTransform(),
        "metadata": dict(clip.metadata()),
        "tags": _tags(clip),
        "media": {
            "filename": info.filename(),
            "start_frame": info.startFrame(),
            "timecode_start": media.timecodeStart(),
            "single_file": media.singleFile(),
            "padding": media.filenamePadding(),
            "head": media.filenameHead(),
            "duration": media.duration(),
            "width": media.width(),
            "height": media.height(),
            "pixel_aspect": media.pixelAspect(),
            "has_audio": media.hasAudio(),
            "metadata": dict(media.metadata()),
        },
    }


def _dump_effect(effect, first, last):
    data = {
        "name": effect.name(),
        "enabled": effect.isEnabled(),
        "linked": [item.name() for item in effect.linkedItems()],
    }
    if "TimeWarp" in effect.name():
        node = effect.node()
        try:
            data["node"] = {
                "name": {"value": node["name"].value()},
                "lookup": _knob(node["lookup"], first, last),
                "length": _knob(node["length"], first, last),
            }
        except Exception as exc:  # noqa: BLE001
            print("DUMP WARNING: effect {}: {}".format(effect.name(), exc))
            data["enabled"] = False
    return data


def dump_sequence(sequence):
    """Read a Hiero sequence into the input dict of the reference."""
    clips, tracks = {}, []
    for track in sequence.items():
        items = []
        first = last = 0
        for index, item in enumerate(track):
            key = "{}:{}".format(track.name(), index)
            clips[key] = _dump_clip(item.source())
            items.append({
                "name": item.name(),
                "clip": key,
                "timeline_in": item.timelineIn(),
                "timeline_out": item.timelineOut(),
                "source_in": item.sourceIn(),
                "source_out": item.sourceOut(),
                "speed": item.playbackSpeed(),
                "tags": _tags(item),
            })
        effects = []
        for group in track.subTrackItems():
            dumped = []
            for effect in _flatten(group):
                # sampled over the span of every item it may touch
                linked = effect.linkedItems() or list(track)
                if not linked:
                    continue
                first = min(item.timelineIn() for item in linked)
                last = max(item.timelineOut() for item in linked)
                dumped.append(_dump_effect(effect, first, last))
            effects.append(dumped)
        tracks.append({
            "name": track.name(),
            "kind": (
                "audio" if isinstance(track, hiero.core.AudioTrack)
                else "video"
            ),
            "enabled": track.isEnabled(),
            "items": items,
            "effects": effects,
            "tags": _tags(track),
        })

    project = sequence.project()
    fmt = sequence.format()
    return {
        "name": sequence.name(),
        "framerate": _rational(sequence),
        "timecode_start": sequence.timecodeStart(),
        "metadata": dict(sequence.metadata()),
        "format": {
            "width": fmt.width(),
            "height": fmt.height(),
            "pixel_aspect": fmt.pixelAspect(),
        },
        "project": {key: getattr(project, key)() for key in PROJECT_KEYS},
        "clips": clips,
        "tracks": tracks,
    }


def _load_reference():
    path = os.path.join(
        EDITORIAL_REPO, "tests", "resources", "host_exports",
        "hiero_reference.py",
    )
    spec = importlib.util.spec_from_file_location("hiero_reference", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _import_compare():
    try:
        from ayon_editorial.otio import compare
        return compare
    except ImportError:
        pass
    if not EDITORIAL_CLIENT:
        raise RuntimeError(
            "ayon_editorial is not importable: set EDITORIAL_CLIENT."
        )
    # Plain package object: skips `ayon_editorial/__init__` (ayon_core).
    package = types.ModuleType("ayon_editorial")
    package.__path__ = [os.path.join(EDITORIAL_CLIENT, "ayon_editorial")]
    sys.modules["ayon_editorial"] = package
    from ayon_editorial.otio import compare
    return compare


def run():
    from ayon_hiero.api.otio import hiero_export

    sequence = hiero.ui.activeSequence()
    if sequence is None:
        print("No active sequence.")
        return
    compare = _import_compare()

    expected = _load_reference().export(dump_sequence(sequence))
    actual = hiero_export.create_otio_timeline(sequence)

    diffs = compare.compare_timelines(expected, actual)
    if diffs:
        print("{} difference(s), left = reference, right = new:".format(
            len(diffs)))
        print(compare.format_differences(diffs))
    else:
        print("OK")


run()
