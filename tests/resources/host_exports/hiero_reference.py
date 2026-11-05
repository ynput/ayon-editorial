"""Hiero export code (OTIO timeline), run without Hiero.

Reference exporter fixture for the P2.6 builder comparison. The export
functions are copied verbatim from the host; only the host reads are served
by the small fake classes below, which are built from a plain input dict
(`hiero_input.json`). The copied lines are not edited. A line that had to
change ends with `# HOST-READ`.

Host repo: ynput/ayon-hiero
Host file: client/ayon_hiero/api/otio/hiero_export.py
  commit:    88fbaf74fc0a62800d7112f3bf184653e0e94c21
  git blob:  7b006f3c5b103314f1f1c0ff05bc3b9a0add9135
  copied:    L13-L433 (constants, CTX, flatten ... create_otio_timeline);
             L1-L11 (docstring, imports) replaced, L436-L437
             (write_to_file) not copied
Host file: client/ayon_hiero/api/otio/utils.py
  commit:    402c5fd1b15978701ee9b27a42aef6f778190a36
  git blob:  f1b3cffa38f4e34e88f0cb0b3b55d9f8897ba71e
  copied:    L22-L44 (get_reformated_path), L68-L82 (get_rate)

Independent of `ayon_editorial` on purpose. Needs only opentimelineio.
"""
# ruff: noqa: E501
# fmt: off
import re  # HOST-READ (imports of the host replaced by the lines below)
import os
import types
from typing import Optional

import opentimelineio as otio


# --- fake Hiero objects, served from the input dict ------------------------
class _Rational:
    def __init__(self, num, den):
        self.num = num
        self.den = den

    def toRational(self):
        return (self.num, self.den)

    def toFloat(self):
        return float(self.num) / float(self.den)


class Tag:
    def __init__(self, data):
        self._data = data

    def name(self):
        return self._data["name"]

    def icon(self):
        return self._data.get("icon", "")

    def visible(self):
        return self._data.get("visible", True)

    def inTime(self):
        return self._data.get("in_time", 0)

    def metadata(self):
        return _TagMetadata(self._data.get("metadata", {}))


class _TagMetadata:
    def __init__(self, data):
        self._data = data

    def dict(self):
        return dict(self._data)


def _tags(data):
    return [Tag(tag) for tag in data.get("tags", [])]


class FileInfo:
    def __init__(self, data):
        self._data = data

    def startFrame(self):
        return self._data["start_frame"]

    def filename(self):
        return self._data["filename"]


class MediaSource:
    def __init__(self, data):
        self._data = data

    def fileinfos(self):
        return [FileInfo(self._data)]

    def timecodeStart(self):
        return self._data["timecode_start"]

    def filenamePadding(self):
        return self._data.get("padding", 0)

    def filenameHead(self):
        return self._data.get("head", "")

    def singleFile(self):
        return self._data["single_file"]

    def duration(self):
        return self._data["duration"]

    def width(self):
        return self._data["width"]

    def height(self):
        return self._data["height"]

    def pixelAspect(self):
        return self._data.get("pixel_aspect", 1.0)

    def hasAudio(self):
        return self._data.get("has_audio", False)

    def metadata(self):
        return dict(self._data.get("metadata", {}))


class Clip:
    def __init__(self, data):
        self._data = data

    def metadata(self):
        return dict(self._data.get("metadata", {}))

    def mediaSource(self):
        return MediaSource(self._data["media"])

    def sourceMediaColourTransform(self):
        return self._data.get("colour_transform", "")

    def framerate(self):
        return _Rational(*self._data["framerate"])

    def tags(self):
        return _tags(self._data)


class Knob:
    def __init__(self, data):
        self._data = data

    def value(self):
        return self._data["value"]

    def isAnimated(self):
        return "curve" in self._data

    def getValueAt(self, frame):
        # linear between the keys, held outside of them
        keys = self._data["curve"]
        if frame <= keys[0][0]:
            return keys[0][1]
        for (f_a, v_a), (f_b, v_b) in zip(keys, keys[1:]):
            if frame <= f_b:
                return v_a + (v_b - v_a) * (frame - f_a) / (f_b - f_a)
        return keys[-1][1]


class Node:
    def __init__(self, data):
        self._data = data

    def __getitem__(self, name):
        return Knob(self._data[name])


class SubTrackItem:
    def __init__(self, data, track):
        self._data = data
        self._track = track

    def name(self):
        return self._data["name"]

    def isEnabled(self):
        return self._data.get("enabled", True)

    def linkedItems(self):
        names = self._data.get("linked", [])
        return [item for item in self._track.items() if item.name() in names]

    def node(self):
        return Node(self._data["node"])


class TrackItem:
    def __init__(self, data, track, clips):
        self._data = data
        self._track = track
        self._clip = Clip(clips[data["clip"]])

    def parent(self):
        return self._track

    def source(self):
        return self._clip

    def name(self):
        return self._data["name"]

    def framerate(self):
        return self._clip.framerate()

    def playbackSpeed(self):
        return self._data.get("speed", 1.0)

    def sourceIn(self):
        return self._data["source_in"]

    def sourceOut(self):
        return self._data["source_out"]

    def timelineIn(self):
        return self._data["timeline_in"]

    def timelineOut(self):
        return self._data["timeline_out"]

    def duration(self):
        return self.timelineOut() - self.timelineIn() + 1

    def tags(self):
        return _tags(self._data)


class _Track:
    def __init__(self, data, clips):
        self._data = data
        self._items = [TrackItem(item, self, clips) for item in data["items"]]
        self._sub_items = [
            [SubTrackItem(effect, self) for effect in group]
            for group in data.get("effects", [])
        ]

    def name(self):
        return self._data["name"]

    def isEnabled(self):
        return self._data.get("enabled", True)

    def items(self):
        return list(self._items)

    def subTrackItems(self):
        return self._sub_items

    def tags(self):
        return _tags(self._data)

    def __iter__(self):
        return iter(self._items)


class VideoTrack(_Track):
    pass


class AudioTrack(_Track):
    pass


class _Project:
    def __init__(self, data):
        self._data = data

    def __getattr__(self, name):
        return lambda: self._data[name]


class _Format:
    def __init__(self, data):
        self._data = data

    def width(self):
        return self._data["width"]

    def height(self):
        return self._data["height"]

    def pixelAspect(self):
        return self._data["pixel_aspect"]


class Sequence:
    def __init__(self, data):
        self._data = data
        clips = data["clips"]
        self._tracks = [
            (AudioTrack if track["kind"] == "audio" else VideoTrack)(
                track, clips)
            for track in data["tracks"]
        ]

    def name(self):
        return self._data["name"]

    def metadata(self):
        return dict(self._data.get("metadata", {}))

    def project(self):
        return _Project(self._data["project"])

    def format(self):
        return _Format(self._data["format"])

    def timecodeStart(self):
        return self._data["timecode_start"]

    def framerate(self):
        return _Rational(*self._data["framerate"])

    def items(self):
        return list(self._tracks)


hiero = types.SimpleNamespace(  # HOST-READ
    core=types.SimpleNamespace(
        VideoTrack=VideoTrack, AudioTrack=AudioTrack, Sequence=Sequence),
    ui=types.SimpleNamespace(activeSequence=lambda: None),
)


# --- copied from utils.py (L22-L44, L68-L82) -------------------------------
def get_reformated_path(path, padded=True):
    """
    Return fixed python expression path

    Args:
        path (str): path url or simple file name

    Returns:
        type: string with reformatted path

    Example:
        get_reformated_path("plate.[0001-1008].exr") > plate.%04d.exr

    """
    if "%" in path:
        padding_pattern = r"(\d+)"
        padding = int(re.findall(padding_pattern, path).pop())
        num_pattern = r"(%\d+d)"
        if padded:
            path = re.sub(num_pattern, "%0{}d".format(padding), path)
        else:
            path = re.sub(num_pattern, "%d", path)
    return path


def get_rate(item):
    if not hasattr(item, 'framerate'):
        return None

    num, den = item.framerate().toRational()

    try:
        rate = float(num) / float(den)
    except ZeroDivisionError:
        return None

    if rate.is_integer():
        return rate

    return round(rate, 4)


utils = types.SimpleNamespace(  # HOST-READ
    get_rate=get_rate, get_reformated_path=get_reformated_path)


# --- copied from hiero_export.py (L13-L433) --------------------------------
TRACK_TYPE_MAP = {
    hiero.core.VideoTrack: otio.schema.TrackKind.Video,
    hiero.core.AudioTrack: otio.schema.TrackKind.Audio
}
MARKER_COLOR_MAP = {
    "magenta": otio.schema.MarkerColor.MAGENTA,
    "red": otio.schema.MarkerColor.RED,
    "yellow": otio.schema.MarkerColor.YELLOW,
    "green": otio.schema.MarkerColor.GREEN,
    "cyan": otio.schema.MarkerColor.CYAN,
    "blue": otio.schema.MarkerColor.BLUE,
}


class CTX:
    project_fps = None
    timeline = None
    include_tags = True


def flatten(list_):
    for item_ in list_:
        if isinstance(item_, (list, tuple)):
            for sub_item in flatten(item_):
                yield sub_item
        else:
            yield item_


def create_otio_rational_time(frame, fps):
    return otio.opentime.RationalTime(
        float(frame),
        float(fps)
    )


def create_otio_time_range(start_frame, frame_duration, fps):
    return otio.opentime.TimeRange(
        start_time=create_otio_rational_time(start_frame, fps),
        duration=create_otio_rational_time(frame_duration, fps)
    )


def _get_metadata(item):
    if hasattr(item, 'metadata'):
        return {key: value for key, value in dict(item.metadata()).items()}
    return {}


def create_time_effects(otio_clip, track_item):
    # get all subtrack items
    subTrackItems = flatten(track_item.parent().subTrackItems())
    speed = track_item.playbackSpeed()

    otio_effect = None
    # retime on track item
    if speed != 1.:
        # make effect
        otio_effect = otio.schema.LinearTimeWarp()
        otio_effect.name = "Speed"
        otio_effect.time_scalar = speed

    # freeze frame effect
    if speed == 0.:
        otio_effect = otio.schema.FreezeFrame()
        otio_effect.name = "FreezeFrame"

    if otio_effect:
        # add otio effect to clip effects
        otio_clip.effects.append(otio_effect)

    # loop through and get all Timewarps
    for effect in subTrackItems:
        if ((track_item not in effect.linkedItems())
                and (len(effect.linkedItems()) > 0)):
            continue
        # avoid all effect which are not TimeWarp and disabled
        if "TimeWarp" not in effect.name():
            continue

        if not effect.isEnabled():
            continue

        node = effect.node()
        name = node["name"].value()

        # solve effect class as effect name
        _name = effect.name()
        if "_" in _name:
            effect_name = re.sub(r"(?:_)[_0-9]+", "", _name)  # more numbers
        else:
            effect_name = re.sub(r"\d+", "", _name)  # one number

        metadata = {}
        # add knob to metadata
        for knob in ["lookup", "length"]:
            value = node[knob].value()
            animated = node[knob].isAnimated()
            if animated:
                value = [
                    ((node[knob].getValueAt(i)) - i)
                    for i in range(
                        track_item.timelineIn(), track_item.timelineOut() + 1)
                ]

            metadata[knob] = value

        # make effect
        otio_effect = otio.schema.TimeEffect()
        otio_effect.name = name
        otio_effect.effect_name = effect_name
        otio_effect.metadata.update(metadata)

        # add otio effect to clip effects
        otio_clip.effects.append(otio_effect)


def create_otio_reference(clip):
    metadata = _get_metadata(clip)
    media_source = clip.mediaSource()

    # get file info for path and start frame
    file_info = media_source.fileinfos().pop()
    start_frame = file_info.startFrame()
    timecode_start = media_source.timecodeStart()
    path = file_info.filename()

    # get padding and other file infos
    padding = media_source.filenamePadding()
    file_head = media_source.filenameHead()
    is_sequence = not media_source.singleFile()
    frame_duration = media_source.duration()
    fps = utils.get_rate(clip) or CTX.project_fps
    extension = os.path.splitext(path)[-1]

    if is_sequence:
        metadata.update({
            "isSequence": True,
            "padding": padding
        })

    # add resolution metadata
    metadata.update({
        "ayon.source.colorspace": clip.sourceMediaColourTransform(),
        "ayon.source.width": int(media_source.width()),
        "ayon.source.height": int(media_source.height()),
        "ayon.source.pixelAspect": float(media_source.pixelAspect())
    })

    otio_ex_ref_item = None

    if is_sequence:
        # if it is file sequence try to create `ImageSequenceReference`
        # the OTIO might not be compatible so return nothing and do it old way
        try:
            dirname = os.path.dirname(path)
            otio_ex_ref_item = otio.schema.ImageSequenceReference(
                target_url_base=dirname + os.sep,
                name_prefix=file_head,
                name_suffix=extension,
                start_frame=start_frame,
                frame_zero_padding=padding,
                rate=fps,
                available_range=create_otio_time_range(
                    timecode_start,
                    frame_duration,
                    fps
                )
            )
        except AttributeError:
            pass

    if not otio_ex_ref_item:
        reformat_path = utils.get_reformated_path(path, padded=False)
        # in case old OTIO or video file create `ExternalReference`
        otio_ex_ref_item = otio.schema.ExternalReference(
            target_url=reformat_path,
            available_range=create_otio_time_range(
                timecode_start,
                frame_duration,
                fps
            )
        )

    # add metadata to otio item
    add_otio_metadata(otio_ex_ref_item, media_source, **metadata)

    return otio_ex_ref_item


def get_marker_color(tag):
    icon = tag.icon()
    pat = r'icons:Tag(?P<color>\w+)\.\w+'

    res = re.search(pat, icon)
    if res:
        color = res.groupdict().get('color')
        if color.lower() in MARKER_COLOR_MAP:
            return MARKER_COLOR_MAP[color.lower()]

    return otio.schema.MarkerColor.RED


def create_otio_markers(otio_item, item):
    for tag in item.tags():
        if not tag.visible():
            continue

        if tag.name() == 'Copy':
            # Hiero adds this tag to a lot of clips
            continue

        frame_rate = utils.get_rate(item) or CTX.project_fps

        marked_range = otio.opentime.TimeRange(
            start_time=otio.opentime.RationalTime(
                tag.inTime(),
                frame_rate
            ),
            duration=otio.opentime.RationalTime(
                int(tag.metadata().dict().get('tag.length', '0')),
                frame_rate
            )
        )
        # add tag metadata but remove "tag." string
        metadata = {}

        for key, value in tag.metadata().dict().items():
            _key = key.replace("tag.", "")

            metadata.update({_key: value})

        # Store the source item for future import assignment
        metadata['hiero_source_type'] = item.__class__.__name__

        marker = otio.schema.Marker(
            name=tag.name(),
            color=get_marker_color(tag),
            marked_range=marked_range,
            metadata=metadata
        )

        otio_item.markers.append(marker)


def create_otio_clip(track_item):
    clip = track_item.source()
    speed = track_item.playbackSpeed()
    # flip if speed is in minus
    source_in = track_item.sourceIn() if speed > 0 else track_item.sourceOut()

    duration = int(track_item.duration())

    fps = utils.get_rate(track_item) or CTX.project_fps
    name = track_item.name()

    media_reference = create_otio_reference(clip)
    available_start = media_reference.available_range.start_time
    source_in_offset = otio.opentime.RationalTime(
        source_in,
        available_start.rate
    )
    src_in = available_start + source_in_offset
    conformed_src_in = src_in.rescaled_to(fps)

    source_range = create_otio_time_range(
        conformed_src_in.value,  # no rounding to preserve accuracy
        duration,
        fps
    )

    otio_clip = otio.schema.Clip(
        name=name,
        source_range=source_range,
        media_reference=media_reference
    )

    # Add tags as markers
    if CTX.include_tags:
        create_otio_markers(otio_clip, track_item)
        create_otio_markers(otio_clip, track_item.source())

    # only if video
    if not clip.mediaSource().hasAudio():
        # Add effects to clips
        create_time_effects(otio_clip, track_item)

    return otio_clip


def create_otio_gap(gap_start, clip_start, tl_start_frame, fps):
    return otio.schema.Gap(
        source_range=create_otio_time_range(
            gap_start,
            (clip_start - tl_start_frame) - gap_start,
            fps
        )
    )


def _create_otio_timeline():
    project = CTX.timeline.project()
    metadata = _get_metadata(CTX.timeline)

    metadata.update({
        "ayon.timeline.width": int(CTX.timeline.format().width()),
        "ayon.timeline.height": int(CTX.timeline.format().height()),
        "ayon.timeline.pixelAspect": int(CTX.timeline.format().pixelAspect()),  # noqa
        "ayon.project.useOCIOEnvironmentOverride": project.useOCIOEnvironmentOverride(),  # noqa
        "ayon.project.lutSetting16Bit": project.lutSetting16Bit(),
        "ayon.project.lutSetting8Bit": project.lutSetting8Bit(),
        "ayon.project.lutSettingFloat": project.lutSettingFloat(),
        "ayon.project.lutSettingLog": project.lutSettingLog(),
        "ayon.project.lutSettingViewer": project.lutSettingViewer(),
        "ayon.project.lutSettingWorkingSpace": project.lutSettingWorkingSpace(),  # noqa
        "ayon.project.lutUseOCIOForExport": project.lutUseOCIOForExport(),
        "ayon.project.ocioConfigName": project.ocioConfigName(),
        "ayon.project.ocioConfigPath": project.ocioConfigPath()
    })

    start_time = create_otio_rational_time(
        CTX.timeline.timecodeStart(), CTX.project_fps)

    return otio.schema.Timeline(
        name=CTX.timeline.name(),
        global_start_time=start_time,
        metadata=metadata
    )


def create_otio_track(track_type, track_name):
    return otio.schema.Track(
        name=track_name,
        kind=TRACK_TYPE_MAP[track_type]
    )


def add_otio_gap(track_item, otio_track, prev_out):
    gap_length = track_item.timelineIn() - prev_out
    if prev_out != 0:
        gap_length -= 1

    gap = otio.opentime.TimeRange(
        duration=otio.opentime.RationalTime(
            gap_length,
            CTX.project_fps
        )
    )
    otio_gap = otio.schema.Gap(source_range=gap)
    otio_track.append(otio_gap)


def add_otio_metadata(otio_item, media_source, **kwargs):
    metadata = _get_metadata(media_source)

    # add additional metadata from kwargs
    if kwargs:
        metadata.update(kwargs)

    # add metadata to otio item metadata
    for key, value in metadata.items():
        otio_item.metadata.update({key: value})


def create_otio_timeline(
    sequence: Optional[hiero.core.Sequence] = None,
) -> otio.schema.Timeline:

    # get current timeline
    CTX.timeline = sequence or hiero.ui.activeSequence()
    CTX.project_fps = CTX.timeline.framerate().toFloat()

    # convert timeline to otio
    otio_timeline = _create_otio_timeline()

    # loop all defined track types
    for track in CTX.timeline.items():
        # skip if track is disabled
        if not track.isEnabled():
            continue

        # convert track to otio
        otio_track = create_otio_track(
            type(track), track.name())

        for itemindex, track_item in enumerate(track):
            # Add Gap if needed
            if itemindex == 0:
                # if it is first track item at track then add
                # it to previous item
                prev_item = track_item

            else:
                # get previous item
                prev_item = track_item.parent().items()[itemindex - 1]

            # calculate clip frame range difference from each other
            clip_diff = track_item.timelineIn() - prev_item.timelineOut()

            # add gap if first track item is not starting
            # at first timeline frame
            if itemindex == 0 and track_item.timelineIn() > 0:
                add_otio_gap(track_item, otio_track, 0)

            # or add gap if following track items are having
            # frame range differences from each other
            elif itemindex and clip_diff != 1:
                add_otio_gap(track_item, otio_track, prev_item.timelineOut())

            # create otio clip and add it to track
            otio_clip = create_otio_clip(track_item)
            otio_track.append(otio_clip)

        # Add tags as markers
        if CTX.include_tags:
            create_otio_markers(otio_track, track)

        # add track to otio timeline
        otio_timeline.tracks.append(otio_track)

    return otio_timeline


# fmt: on
def export(data: dict) -> otio.schema.Timeline:
    """Run the host export on the plain input dict (`hiero_input.json`)."""
    CTX.include_tags = True  # HOST-READ (reset the module state)
    return create_otio_timeline(Sequence(data))  # HOST-READ
