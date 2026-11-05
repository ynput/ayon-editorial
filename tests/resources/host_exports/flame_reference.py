"""Flame reference exporter: the host export code, run without Flame.

Host repo:   ayon-flame
Host path:   client/ayon_flame/otio/flame_export.py
Commit:      a77888fb8ff1018907849e615584499e7736d1bb
Git blob:    1e27519d878ecfbd3b4b7f3bce6743742a8616ed
Helpers:     client/ayon_flame/otio/utils.py, git blob
             a94c1687b67b88d7f2c526147f7b9dc607880c3d

Copied verbatim from `flame_export.py` (line numbers of that blob):
    25-42 (track types, marker colours), 45-72 (`OtioExportCTX`),
    75-81 (`flatten`), 89-100 (rational time, time range),
    103-106 (`_get_metadata`), 109-169 (`create_time_effects`),
    172-254 (markers), 257-378 (`create_otio_reference`),
    381-505 (`create_otio_clip`), 508-515 (`create_otio_gap`),
    538-559 (`_create_otio_timeline`), 562-566 (`create_otio_track`),
    569-581 (`add_otio_gap`), 584-593 (`add_otio_metadata`),
    616-640 (`_get_segments_from_track`),
    643-678 (`_distribute_segments_on_track`),
    681-759 (`create_otio_timeline`).
Copied verbatim from `utils.py`: 11 (`FRAME_PATTERN`),
    14-16 (`timecode_to_frames`), 29-56 (`get_reformatted_filename`),
    59-75 (`get_padding_from_filename`), 78-101
    (`get_frame_from_filename`).
Not copied: `get_current_flame_project` (84-86), `_get_colourspace_policy`
    (518-535) and `_get_shot_tokens_values` (596-613), all Flame reads, and
    `write_to_file` (762-763).

One host comment gets a trailing `# codespell:ignore` (L903, `inbetween`).
Otherwise only host reads are replaced, by small fake classes built from
the plain input dict (`flame_input.json`); every such line ends in
`# HOST-READ`.
Do not edit the copied code: re-copy it when the host file changes.
"""

from __future__ import annotations

import json
import logging
import os
import re
import types
from pprint import pformat

import opentimelineio as otio

# --- HOST-READ replacements ------------------------------------------------

# fmt: off

# `from ayon_core.lib.transcoding import IMAGE_EXTENSIONS`
IMAGE_EXTENSIONS = {  # HOST-READ
    ".bmp", ".dpx", ".exr", ".gif", ".jpeg", ".jpg", ".png", ".tif",  # HOST-READ  # noqa: E501
    ".tiff", ".tga", ".hdr",  # HOST-READ
}  # HOST-READ

log = logging.getLogger(__name__)

# State of the current `export()` call.
_STATE = {}  # HOST-READ


class _Attr:  # HOST-READ
    """Flame `PyAttribute` stand-in: `get_value()` returns the value."""  # HOST-READ  # noqa: E501

    def __init__(self, value):  # HOST-READ
        self._value = value  # HOST-READ

    def get_value(self):  # HOST-READ
        return self._value  # HOST-READ


class _Time:  # HOST-READ
    """Flame `PyTime` stand-in with the `relative_frame` read."""  # HOST-READ

    def __init__(self, frame):  # HOST-READ
        self.relative_frame = frame  # HOST-READ


class _Marker:  # HOST-READ
    def __init__(self, data):  # HOST-READ
        self.name = _Attr(data["name"])  # HOST-READ
        self.duration = _Attr(_Time(data["duration"]))  # HOST-READ
        self.comment = _Attr(data["comment"])  # HOST-READ
        self.location = _Attr(_Time(data["location"]))  # HOST-READ
        self.colour = _Attr(data["colour"])  # HOST-READ


class _Segment:  # HOST-READ
    """Flame `PySegment` stand-in built from one input segment dict."""  # HOST-READ  # noqa: E501

    def __init__(self, data):  # HOST-READ
        self.data = data  # HOST-READ
        self.type = data.get("type", "Video")  # HOST-READ
        self.name = _Attr(data.get("name", ""))  # HOST-READ
        self.shot_name = _Attr("")  # HOST-READ
        self.comment = _Attr("")  # HOST-READ
        self.tape_name = ""  # HOST-READ
        self.source_name = ""  # HOST-READ
        self.file_path = data.get("file_path", "")  # HOST-READ
        self.record_in = _Time(data["record_in"])  # HOST-READ
        self.markers = [_Marker(m) for m in data.get("markers", [])]  # HOST-READ  # noqa: E501


class _Track:  # HOST-READ
    def __init__(self, data):  # HOST-READ
        self.name = "'{}'".format(data["name"])  # HOST-READ
        self.hidden = _Attr(data.get("hidden", False))  # HOST-READ
        self.segments = [_Segment(s) for s in data.get("segments", [])]  # HOST-READ  # noqa: E501


class _Version:  # HOST-READ
    def __init__(self, data):  # HOST-READ
        self.tracks = [_Track(t) for t in data]  # HOST-READ


class _AudioTrack:  # HOST-READ
    def __init__(self, data):  # HOST-READ
        self.name = data["name"]  # HOST-READ
        self.stereo = data.get("stereo", False)  # HOST-READ
        self.channels = [_Track(c) for c in data["channels"]]  # HOST-READ


class _Sequence:  # HOST-READ
    """Flame `PySequence` stand-in built from the input dict."""  # HOST-READ

    def __init__(self, data):  # HOST-READ
        self.name = "'{}'".format(data["name"])  # HOST-READ
        self.frame_rate = "{} fps".format(data["frame_rate"])  # HOST-READ
        self.start_time = data["start_time"]  # HOST-READ
        self.width = data["width"]  # HOST-READ
        self.height = data["height"]  # HOST-READ
        self.attributes = {}  # HOST-READ
        self.versions = [_Version(v) for v in data["versions"]]  # HOST-READ
        self.audio_tracks = [  # HOST-READ
            _AudioTrack(a) for a in data.get("audio_tracks", [])  # HOST-READ
        ]  # HOST-READ


class MediaInfoFile:  # HOST-READ
    """Fake `ayon_flame.api.MediaInfoFile`: probe values from the input."""  # HOST-READ  # noqa: E501

    def __init__(self, path, logger=None):  # HOST-READ
        info = _STATE["media_info"][path]  # HOST-READ
        self.start_frame = info["start_frame"]  # HOST-READ
        self.fps = info["fps"]  # HOST-READ
        self.file_pattern = info.get("file_pattern", path)  # HOST-READ
        if "width" in info:  # HOST-READ
            self.width = info["width"]  # HOST-READ
            self.height = info["height"]  # HOST-READ
            self.pixel_aspect = info["pixel_aspect"]  # HOST-READ


class TimeEffectMetadata:  # HOST-READ
    """Fake `ayon_flame.api.TimeEffectMetadata`: values from the input."""  # HOST-READ  # noqa: E501

    def __init__(self, segment, logger=None):  # HOST-READ
        effect = segment.data.get("time_effect") or {}  # HOST-READ
        self.is_empty = effect.get("is_empty", True)  # HOST-READ
        self.data = effect.get("data", {})  # HOST-READ
        # baked frames, what `tw_bake` would compute from the Flame XML
        self.setup_data = effect.get("iframes", {})  # HOST-READ


class _Timewarp:  # HOST-READ
    def bake_flame_tw_setup(self, setup_data):  # HOST-READ
        return setup_data  # HOST-READ


tw_bake = types.SimpleNamespace(Timewarp=_Timewarp)  # HOST-READ


class _ValidationAggregator:  # HOST-READ
    def __init__(self):  # HOST-READ
        self.failed_segments = []  # HOST-READ


def _get_segment_attributes(segment, validation_aggregator=None):  # HOST-READ
    """Segment attributes as `lib.get_segment_attributes` returns them."""  # HOST-READ  # noqa: E501
    if segment.type == "Gap":  # HOST-READ
        return None  # HOST-READ
    data = segment.data  # HOST-READ
    clip_data = {  # HOST-READ
        "PySegment": segment,  # HOST-READ
        "segment_name": data.get("name") or "Missing: Segment's Name",  # HOST-READ  # noqa: E501
        "fpath": "",  # HOST-READ
    }  # HOST-READ
    if segment.file_path and data.get("name"):  # HOST-READ
        clip_data["fpath"] = segment.file_path  # HOST-READ
    else:  # HOST-READ
        clip_data["segment_name"] = "Missing: Segment's File Path"  # HOST-READ
    for key in (  # HOST-READ
        "record_duration", "record_in", "record_out", "source_in",  # HOST-READ
        "source_out", "source_frame_rate", "start_frame",  # HOST-READ
    ):  # HOST-READ
        if key in data:  # HOST-READ
            clip_data[key] = data[key]  # HOST-READ
    return clip_data  # HOST-READ


lib = types.SimpleNamespace(  # HOST-READ
    ValidationAggregator=_ValidationAggregator,  # HOST-READ
    get_segment_attributes=_get_segment_attributes,  # HOST-READ
)  # HOST-READ


def get_current_flame_project():  # HOST-READ
    return types.SimpleNamespace(name=_STATE["project"])  # HOST-READ


def _get_colourspace_policy():  # HOST-READ
    # host: parses /opt/Autodesk/project/<name>/synColor/policy/policy.cfg
    return dict(_STATE["colourspace_policy"])  # HOST-READ


# --- copied from ayon_flame/otio/utils.py ----------------------------------

FRAME_PATTERN = r"[\._](\d+)"


def timecode_to_frames(timecode, framerate):
    rt = otio.opentime.from_timecode(timecode, framerate)
    return int(otio.opentime.to_frames(rt))


def get_reformatted_filename(filename, padded=True):
    """
    Return fixed python expression path

    Args:
        filename (str): file name

    Returns:
        type: string with reformatted path

    Example:
        get_reformatted_filename("plate.1001.exr") > plate.%04d.exr

    """
    found = FRAME_PATTERN.search(filename)

    if not found:
        log.info("File name is not sequence: {}".format(filename))
        return filename

    padding = get_padding_from_filename(filename)

    replacement = "%0{}d".format(padding) if padded else "%d"
    start_idx, end_idx = found.span(1)

    return replacement.join(
        [filename[:start_idx], filename[end_idx:]]
    )


def get_padding_from_filename(filename):
    """
    Return padding number from Flame path style

    Args:
        filename (str): file name

    Returns:
        int: padding number

    Example:
        get_padding_from_filename("plate.0001.exr") > 4

    """
    found = get_frame_from_filename(filename)

    return len(found) if found else None


def get_frame_from_filename(filename):
    """
    Return sequence number from Flame path style

    Args:
        filename (str): file name

    Returns:
        Optional[str]: sequence frame number if found or None

    Example:
        def get_frame_from_filename(path):
            ("plate.0001.exr") > "0001"

    """
    _, ext = os.path.splitext(filename)

    if ext.lower() not in IMAGE_EXTENSIONS:
        return None

    pattern = re.compile(FRAME_PATTERN + re.escape(ext))
    found = pattern.findall(filename)

    return found.pop() if found else None


utils = types.SimpleNamespace(  # HOST-READ
    timecode_to_frames=timecode_to_frames,  # HOST-READ
    get_reformatted_filename=get_reformatted_filename,  # HOST-READ
    get_frame_from_filename=get_frame_from_filename,  # HOST-READ
)  # HOST-READ

# --- copied from ayon_flame/otio/flame_export.py ---------------------------

TRACK_TYPES = {
    "video": otio.schema.TrackKind.Video,
    "audio": otio.schema.TrackKind.Audio
}
MARKERS_COLOR_MAP = {
    (1.0, 0.0, 0.0): otio.schema.MarkerColor.RED,
    (1.0, 0.5, 0.0): otio.schema.MarkerColor.ORANGE,
    (1.0, 1.0, 0.0): otio.schema.MarkerColor.YELLOW,
    (1.0, 0.5, 1.0): otio.schema.MarkerColor.PINK,
    (1.0, 1.0, 1.0): otio.schema.MarkerColor.WHITE,
    (0.0, 1.0, 0.0): otio.schema.MarkerColor.GREEN,
    (0.0, 1.0, 1.0): otio.schema.MarkerColor.CYAN,
    (0.0, 0.0, 1.0): otio.schema.MarkerColor.BLUE,
    (0.5, 0.0, 0.5): otio.schema.MarkerColor.PURPLE,
    (0.5, 0.0, 1.0): otio.schema.MarkerColor.MAGENTA,
    (0.0, 0.0, 0.0): otio.schema.MarkerColor.BLACK
}
MARKERS_INCLUDE = True


class OtioExportCTX:
    _fps = None
    _tl_start_frame = None
    project = None
    clips = None

    @classmethod
    def set_fps(cls, new_fps):
        if not isinstance(new_fps, float):
            raise TypeError(f"Invalid fps type {type(new_fps)}")
        if cls._fps != new_fps:
            cls._fps = new_fps

    @classmethod
    def get_fps(cls):
        return cls._fps

    @classmethod
    def set_tl_start_frame(cls, number):
        if not isinstance(number, int):
            raise TypeError(
                f"Invalid timeline start frame type {type(number)}")
        if cls._tl_start_frame != number:
            cls._tl_start_frame = number

    @classmethod
    def get_tl_start_frame(cls):
        return cls._tl_start_frame


def flatten(_list):
    for item in _list:
        if isinstance(item, (list, tuple)):
            for sub_item in flatten(item):
                yield sub_item
        else:
            yield item


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
    if hasattr(item, "metadata"):
        return dict(item.metadata) if item.metadata else {}
    return {}


def create_time_effects(otio_clip, clip_data, speed, time_effect=None):
    otio_effect = None

    # Clip has a TimeWarp effect.
    if not time_effect.is_empty:
        data = time_effect.data

        # Check if constant speed retiming
        if data["type"] == "speed" and data.get("numKeys") == 1:
            speed = data["speed"]

        else:
            # Interpolate curves.
            # And retrieve interpolated value per frames.
            tw_obj = tw_bake.Timewarp()
            iframes = tw_obj.bake_flame_tw_setup(
                time_effect.setup_data
            )

            # Flame TWs defines its timing offsets
            # from available range (relative).
            # Map interpolated frames to
            # available_range (absolute).
            av_start = otio_clip.available_range().start_time.to_frames()
            mapped_frames = [
                (av_start + iframe - 1)
                for iframe in iframes.values()
            ]

            # Set Timewarp lookup values as offsets from src_range (relative).
            frame_src_offset = min(
                int(clip_data["source_in"]),
                int(clip_data["source_out"])
            )

            metadata = {"lookup": [
                mapped_frame - (frame_src_offset + idx)
                for idx, mapped_frame in enumerate(mapped_frames)
            ]}
            otio_effect = otio.schema.TimeEffect()
            otio_effect.effect_name = "TimeWarp"
            otio_effect.metadata.update(metadata)

    # Potential constant retimes.
    if otio_effect is None:

        # freeze frame effect
        if speed == 0.:
            otio_effect = otio.schema.FreezeFrame(
                name="FreezeFrame"
            )

        elif speed != 1:
            otio_effect = otio.schema.LinearTimeWarp(
                name="Speed",
                time_scalar=speed
            )

    if otio_effect:
        # add otio effect to clip effects
        otio_clip.effects.append(otio_effect)


def _get_marker_color(flame_colour):
    # clamp colors to closes half numbers
    _flame_colour = [
        (lambda x: round(x * 2) / 2)(c)
        for c in flame_colour]

    for color, otio_color_type in MARKERS_COLOR_MAP.items():
        if _flame_colour == list(color):
            return otio_color_type

    return otio.schema.MarkerColor.RED


def _get_flame_markers(item):
    output_markers = []

    time_in = item.record_in.relative_frame

    for marker in item.markers:
        log.debug(marker)
        start_frame = marker.location.get_value().relative_frame

        start_frame = (start_frame - time_in) + 1

        marker_data = {
            "name": marker.name.get_value(),
            "duration": marker.duration.get_value().relative_frame,
            "comment": marker.comment.get_value(),
            "start_frame": start_frame,
            "colour": marker.colour.get_value()
        }

        output_markers.append(marker_data)

    return output_markers


def create_otio_markers(otio_item, item):
    markers = _get_flame_markers(item)
    for marker in markers:
        frame_rate = OtioExportCTX.get_fps()

        marked_range = otio.opentime.TimeRange(
            start_time=otio.opentime.RationalTime(
                marker["start_frame"],
                frame_rate
            ),
            duration=otio.opentime.RationalTime(
                marker["duration"],
                frame_rate
            )
        )

        # testing the comment if it is not containing json string
        check_if_json = re.findall(
            re.compile(r"[{:}]"),
            marker["comment"]
        )

        # to identify this as json, at least 3 items in the list should
        # be present ["{", ":", "}"]
        metadata = {}
        if len(check_if_json) >= 3:
            # this is json string
            try:
                # capture exceptions which are related to strings only
                metadata.update(
                    json.loads(marker["comment"])
                )
            except ValueError as msg:
                log.error(f"Marker json conversion: {msg}")
        else:
            metadata["comment"] = marker["comment"]

        otio_marker = otio.schema.Marker(
            name=marker["name"],
            color=_get_marker_color(
                marker["colour"]),
            marked_range=marked_range,
            metadata=metadata
        )

        otio_item.markers.append(otio_marker)


def create_otio_reference(
        clip_data: dict,
        media_info: MediaInfoFile | None = None,
        fps: float | None = None
) -> (
    otio.schema.ExternalReference |
    otio.schema.ImageSequenceReference |
    otio.schema.MissingReference
):
    """Create an OTIO reference from Flame clip data.

    Args:
        clip_data (dict): Flame clip data.
        media_info (Optional[MediaInfoFile]): Media information.
        fps (Optional[float]): Frames per second.

    Returns:
        otio.schema.ExternalReference |
        otio.schema.ImageSequenceReference |
        otio.schema.MissingReference: OTIO reference.
    """
    if not media_info:
        log.error("Media info is missing")
        return otio.schema.MissingReference(
            name=clip_data["segment_name"]
        )

    metadata = _get_metadata(clip_data)

    # Add image-based metadata if not a pure audio media
    # TODO: what happens if media is image-based but not width
    # can be reached ?
    # (could use ayon_core.lib.transcoding.get_otio_info_for_input)
    if hasattr(media_info, "width"):
        metadata.update(
            {
                "ayon.source.width": media_info.width,
                "ayon.source.height": media_info.height,
                "ayon.source.pixelAspect": media_info.pixel_aspect,
            }
        )

    duration = int(clip_data["source_duration"])

    # get file info for path and start frame
    media_start = media_info.start_frame or 0
    fps = fps or media_info.fps or OtioExportCTX.get_fps()

    path = clip_data["fpath"]

    file_name = os.path.basename(path)
    file_head, extension = os.path.splitext(file_name)

    # get padding and other file infos
    log.debug(f"_ path: {path}")

    otio_ex_ref_item = None

    sequence_match = re.match(
        # match range pattern e.g. "foo_[1001-1010].ext"
        r".*\[(?P<start_frame>\d*)-(?P<end_frame>\d*)\].?",
        media_info.file_pattern
    )

    if sequence_match:
        frame_number = sequence_match.group("start_frame")
        file_head = file_name.split(frame_number)[0]
        start_frame = int(frame_number)
        padding = len(frame_number)

        metadata.update({
            "isSequence": True,
            "padding": padding
        })

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
                    media_start,
                    duration,
                    fps
                )
            )

        # in case old OTIO create sequence as `ExternalReference`
        except AttributeError:
            dirname, file_name = os.path.split(path)
            file_name = utils.get_reformatted_filename(file_name, padded=False)
            reformated_path = os.path.join(dirname, file_name)
            otio_ex_ref_item = otio.schema.ExternalReference(
                target_url=reformated_path,
                available_range=create_otio_time_range(
                    media_start,
                    duration,
                    fps
                )
            )

    # video/audio file create `ExternalReference`
    else:
        otio_ex_ref_item = otio.schema.ExternalReference(
            target_url=path,
            available_range=create_otio_time_range(
                media_start,
                duration,
                fps
            )
        )

    # add metadata to otio item
    add_otio_metadata(otio_ex_ref_item, clip_data, **metadata)

    return otio_ex_ref_item


def create_otio_clip(clip_data):
    segment = clip_data["PySegment"]

    media_info = None
    file_path = None
    file_first_frame = None
    media_timecode_start = None
    tw_data = None
    media_fps = OtioExportCTX.get_fps()  # fallback from timeline
    if clip_data.get("fpath"):
        file_path = clip_data["fpath"]

        # calculate source in
        media_info = MediaInfoFile(file_path, logger=log)
        media_timecode_start = media_info.start_frame
        media_fps = media_info.fps

        # define first frame
        file_first_frame = utils.get_frame_from_filename(
            file_path)
        if file_first_frame:
            file_first_frame = int(file_first_frame)

        # Timewarp metadata
        tw_data = TimeEffectMetadata(segment, logger=log)
        log.debug(f"__ tw_data: {tw_data.data}")
    # fallback for clips with missing file path
    # they will be added as missing reference clips
    elif clip_data.get("start_frame"):
        file_first_frame = int(clip_data["start_frame"])
        media_timecode_start = file_first_frame
    elif clip_data.get("source_frame_rate"):
        # it returns `23.976 fps`
        media_fps = clip_data["source_frame_rate"].replace(" fps", "")
        media_fps = float(media_fps)

    first_frame = media_timecode_start or file_first_frame or 0

    _clip_source_in = int(clip_data["source_in"])
    _clip_source_out = int(clip_data["source_out"])
    _clip_record_in = clip_data["record_in"]
    _clip_record_out = clip_data["record_out"]
    _clip_record_duration = int(clip_data["record_duration"])

    log.debug(f"file_first_frame: {file_first_frame}")
    log.debug(f"first_frame: {first_frame}")
    log.debug(f"_clip_source_in: {_clip_source_in}")
    log.debug(f"_clip_source_out: {_clip_source_out}")
    log.debug(f"_clip_record_in: {_clip_record_in}")
    log.debug(f"_clip_record_out: {_clip_record_out}")

    # first solve if the reverse timing
    speed = 1
    if clip_data["source_in"] > clip_data["source_out"]:
        source_in = _clip_source_out - int(first_frame)
        source_out = _clip_source_in - int(first_frame)
        speed = -1
    else:
        source_in = _clip_source_in - int(first_frame)
        source_out = _clip_source_out - int(first_frame)

    log.debug(f"_ source_in: {source_in}")
    log.debug(f"_ source_out: {source_out}")

    if file_first_frame:
        log.debug(f"_ file_source_in: {file_first_frame + source_in}")
        log.debug(f"_ file_source_in: {file_first_frame + source_out}")

    source_duration = (source_out - source_in + 1)

    if "source_duration" not in clip_data:
        clip_data["source_duration"] = source_duration

    # secondly check if any change of speed
    if source_duration != _clip_record_duration:
        retime_speed = float(source_duration) / float(_clip_record_duration)
        log.debug(f"_ calculated speed: {retime_speed}")
        speed *= retime_speed

    log.debug(f"_ speed: {speed}")
    log.debug(f"_ source_duration: {source_duration}")
    log.debug(f"_ _clip_record_duration: {_clip_record_duration}")

    # create media reference
    if media_info:
        media_reference = create_otio_reference(
            clip_data, media_info=media_info, fps=media_fps)

        # create source range
        available_media_start = media_reference.available_range.start_time
        source_in_offset = otio.opentime.RationalTime(
            source_in,
            available_media_start.rate
        )
        src_in = available_media_start + source_in_offset
        conformed_src_in = src_in.rescaled_to(OtioExportCTX.get_fps())
    else:
        media_reference = create_otio_reference(
            clip_data, fps=media_fps
        )
        conformed_src_in = otio.opentime.RationalTime(
            source_in,
            OtioExportCTX.get_fps()
        )

    source_range = create_otio_time_range(
        conformed_src_in.value,  # no rounding to preserve accuracy
        _clip_record_duration,
        OtioExportCTX.get_fps()
    )

    otio_clip = otio.schema.Clip(
        name=clip_data["segment_name"],
        source_range=source_range,
        media_reference=media_reference
    )

    # Add markers
    if MARKERS_INCLUDE:
        create_otio_markers(otio_clip, segment)

    if tw_data:
        create_time_effects(otio_clip, clip_data, speed, time_effect=tw_data)

    return otio_clip


def create_otio_gap(gap_start, clip_start, tl_start_frame, fps):
    return otio.schema.Gap(
        source_range=create_otio_time_range(
            gap_start,
            (clip_start - tl_start_frame) - gap_start,
            fps
        )
    )


def _create_otio_timeline(sequence):

    metadata = _get_metadata(sequence)

    # find colour policy files and add them to metadata
    colorspace_policy = _get_colourspace_policy()
    metadata.update(colorspace_policy)

    metadata.update({
        "ayon.timeline.width": int(sequence.width),
        "ayon.timeline.height": int(sequence.height),
        "ayon.timeline.pixelAspect": float(1)
    })

    rt_start_time = create_otio_rational_time(
        OtioExportCTX.get_tl_start_frame(), OtioExportCTX.get_fps())

    return otio.schema.Timeline(
        name=str(sequence.name)[1:-1],
        global_start_time=rt_start_time,
        metadata=metadata
    )


def create_otio_track(track_type, track_name):
    return otio.schema.Track(
        name=track_name,
        kind=TRACK_TYPES[track_type]
    )


def add_otio_gap(clip_data, otio_track, prev_out):
    gap_length = clip_data["record_in"] - prev_out
    if prev_out != 0:
        gap_length -= 1

    gap = otio.opentime.TimeRange(
        duration=otio.opentime.RationalTime(
            gap_length,
            OtioExportCTX.get_fps()
        )
    )
    otio_gap = otio.schema.Gap(source_range=gap)
    otio_track.append(otio_gap)


def add_otio_metadata(otio_item, item, **kwargs):
    metadata = _get_metadata(item)

    # add additional metadata from kwargs
    if kwargs:
        metadata.update(kwargs)

    # add metadata to otio item metadata
    for key, value in metadata.items():
        otio_item.metadata.update({key: value})


def _get_segments_from_track(
    flame_track,
    validation_aggregator: lib.ValidationAggregator = None
):
    """Gather segment(s) from a flame track.

    Args:
        flame_track (flame.PyTrack): The Flame track.
        validation_aggregator (lib.ValidationAggregator, optional):
                Output object to store attributes for passing into
                publishing validation. Defaults to None.

    Returns:
        List[flame.PySegment]. The gathered segments.
    """
    if not validation_aggregator:
        validation_aggregator = lib.ValidationAggregator()

    all_segments = []
    for segment in flame_track.segments:
        clip_data = lib.get_segment_attributes(segment, validation_aggregator)
        if clip_data:
            all_segments.append(clip_data)

    return all_segments


def _distribute_segments_on_track(segments, otio_track):
    """Distribute some Flame segments on an OTIO track.

    Args:
        segments List[flame.PySegments]: The segments to put on the track.
        otio_track opentimelineio.schema.Track: OTIO track.
    """
    if not segments:
        return

    prev_item_record_out = segments[0]["record_out"]
    for itemindex, segment_data in enumerate(segments):
        log.debug(f"_ itemindex: {itemindex}")
        log.debug(f"_ segment_data: {segment_data!r}")

        # calculate clip frame range difference from each other
        clip_diff = segment_data["record_in"] - prev_item_record_out

        # initial track gap
        # add gap if first track item is not starting
        # at first timeline frame
        if itemindex == 0 and segment_data["record_in"] > 0:
            add_otio_gap(segment_data, otio_track, 0)

        # inbetween clip gap  # codespell:ignore
        # or add gap if following track items are having
        # frame range differences from each other
        elif itemindex and clip_diff != 1:
            add_otio_gap(
                segment_data, otio_track, prev_item_record_out)

        # create otio clip and add it to track
        otio_clip = create_otio_clip(segment_data)
        log.debug(f"_ otio_clip: {otio_clip!r}")
        otio_track.append(otio_clip)
        prev_item_record_out = segment_data["record_out"]


def create_otio_timeline(
        sequence, validation_aggregator: lib.ValidationAggregator = None):
    if validation_aggregator is None:
        validation_aggregator = lib.ValidationAggregator()

    log.info(dir(sequence))
    log.info(sequence.attributes)

    OtioExportCTX.project = get_current_flame_project()

    # get current timeline
    OtioExportCTX.set_fps(
        float(str(sequence.frame_rate)[:-4]))

    tl_start_frame = utils.timecode_to_frames(
        str(sequence.start_time).replace("+", ":"),
        OtioExportCTX.get_fps()
    )
    OtioExportCTX.set_tl_start_frame(tl_start_frame)

    # convert timeline to otio
    otio_timeline = _create_otio_timeline(sequence)

    # create otio video tracks with clips
    for ver in sequence.versions:
        for track in ver.tracks:
            # avoid all empty tracks
            # or hidden tracks
            if (
                len(track.segments) == 0
                or track.hidden.get_value()
            ):
                continue

            # convert track to otio
            otio_track = create_otio_track(
                "video", str(track.name)[1:-1])

            # Add segments onto track.
            segments = _get_segments_from_track(
                track, validation_aggregator=validation_aggregator)
            log.debug(f"_ segments: {pformat(segments)}")
            _distribute_segments_on_track(segments, otio_track)

            # add track to otio timeline
            otio_timeline.tracks.append(otio_track)

    # create otio audio tracks with clips
    for audio_track in sequence.audio_tracks:

        if (
            len(audio_track.channels) == 0
            and audio_track.stereo and len(audio_track.channels) < 2
        ):
            # Unsupported audio_track do not export.
            log.debug(f"Unsupported audio track: {audio_track!r}")
            continue

        audio_channel = audio_track.channels[0]

        # avoid all empty tracks
        # or hidden tracks
        if (
            len(audio_channel.segments) == 0
            or audio_channel.hidden.get_value()
        ):
            log.debug(f"Hidden or empty channel: {audio_channel!r}")
            continue

        otio_track = create_otio_track(
            "audio", audio_track.name or "unnamed")

        segments = _get_segments_from_track(
            audio_channel, validation_aggregator=validation_aggregator)
        log.debug(f"_ segments: {pformat(segments)}")
        _distribute_segments_on_track(segments, otio_track)
        otio_timeline.tracks.append(otio_track)

    return otio_timeline


# fmt: on

# --- entry point -----------------------------------------------------------


def export(data: dict) -> otio.schema.Timeline:  # HOST-READ
    """Run the host export on the plain input dict.

    Args:
        data (dict): The content of `flame_input.json`.

    Returns:
        otio.schema.Timeline: What the host would export.
    """
    _STATE.clear()  # HOST-READ
    _STATE.update(  # HOST-READ
        project=data["project"],  # HOST-READ
        media_info=data["media_info"],  # HOST-READ
        colourspace_policy=data["colourspace_policy"],  # HOST-READ
    )  # HOST-READ
    return create_otio_timeline(_Sequence(data["sequence"]))  # HOST-READ
