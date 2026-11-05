"""Shot naming, hierarchy and vertical sync of one timeline clip.

Replaces `PublishClip` of ayon-hiero (`api/plugin.py`) and
`PublishableClip` of ayon-flame (`api/plugin.py`). The solver reads a
`ClipInfo` and the creator pre-create values and returns the new clip name
and the tag / marker data. The host keeps the rename (`setName`,
`segment.name =`) and the metadata I/O.
"""
from __future__ import annotations

import logging
import re
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .clip import ClipInfo
from .vertical_sync import VerticalSync

log = logging.getLogger(__name__)

__all__ = ["ShotSolution", "ShotHierarchySolver"]

# Folder type of each hierarchy token (`{track}` makes a sequence folder).
FOLDER_TYPES = {
    "shot": "shot",
    "folder": "folder",
    "episode": "episode",
    "sequence": "sequence",
    "track": "sequence",
}
HIERARCHY_KEYS = ("folder", "episode", "sequence", "track", "shot")

# Used when an option is missing or empty.
HIERARCHY_DEFAULT = "{_folder_}/{_sequence_}/{_track_}"
CLIP_NAME_DEFAULT = "shot_{_trackIndex_:0>3}_{_clipIndex_:0>4}"
VARIANT_DEFAULT = "<track_name>"
COUNT_DEFAULT = 10
HIERARCHY_DATA_DEFAULTS = {
    "folder": "{_folder_}",
    "episode": "ep01",
    "sequence": "{_sequence_}",
    "track": "{_track_}",
    "shot": "{_clip_}",
}

# Pre-create keys that are also part of the returned data.
DATA_KEYS = (
    "hierarchy",
    "folder", "episode", "sequence", "track", "shot",
    "export_audio", "sourceResolution",
    "workfileFrameStart", "handleStart", "handleEnd",
    "includeHandles", "retimedHandles", "retimedFramerange",
    "reviewableSource", "reviewTrackRegexPattern",
)

REGEX_SOURCE = "review_track_regex_pattern"

# Hiero's pattern; the range ` -.` also covers `!"#$%&'()*+`.
# Hiero's name rule; hosts sanitise names in their ClipInfo reader.
HIERO_NAME_PATTERN = re.compile(r"[ -.,]")


def sanitize_name(
    name: str, pattern: "re.Pattern[str]" = HIERO_NAME_PATTERN
) -> str:
    """Replace the characters `pattern` matches with `_`.

    The solver uses names as the host gives them. Hiero sanitises its
    clip and sequence names with `HIERO_NAME_PATTERN`; Flame only
    replaces spaces in the sequence name and keeps clip names.
    """
    return pattern.sub("_", str(name))


_PARENT_TOKEN = re.compile(r"\{([A-Za-z_]*?)\}")
_HASHES = re.compile(r"#+")


@dataclass
class ShotSolution:
    """Result of `ShotHierarchySolver.solve`.

    Attributes:
        new_clip_name: Name the host gives the clip; None when the clip is
            not renamed.
        data: Tag / marker data (newClipName is not part of it).
    """

    new_clip_name: Optional[str]
    data: Dict[str, Any] = field(default_factory=dict)


def _fmt(template: Any, data: Mapping[str, Any], what: str) -> str:
    """`str.format` with a readable error for an unknown token."""
    try:
        return str(template).format(**data)
    except (KeyError, IndexError) as exc:
        raise ValueError(
            f"Unknown token {exc} in {what} '{template}'. "
            f"Known: {sorted(data)}"
        ) from exc


class ShotHierarchySolver:
    """Solve shot names, hierarchy and vertical sync for selected clips.

    Create one per creator run and call `solve` for each clip in the run
    order (vertical sync track first). Instances of one run share the
    `VerticalSync`.

    Args:
        options: Creator pre-create values (hierarchy, clipRename,
            clipName, countFrom, countSteps, folder, episode, sequence,
            track, shot, vSyncOn, vSyncTrack, clipVariant,
            plate_product_type, reviewableSource, reviewTrackRegexPattern,
            useShotName, segmentIndex, ...). Missing or empty values take
            the defaults; `0` and `False` are kept.
        sequence_name: Name of the sequence the clips are on.
        video_track_names: Video track names of the sequence, to resolve
            the review track regex.
        vertical_sync: State shared by the clips of a run.
    """

    def __init__(
        self,
        options: Mapping[str, Any],
        sequence_name: str,
        video_track_names: Sequence[str] = (),
        vertical_sync: Optional[VerticalSync] = None,
    ) -> None:
        self.options = options
        self.sequence_name = str(sequence_name)
        self.video_track_names = list(video_track_names)
        self.vertical_sync = (
            vertical_sync if vertical_sync is not None else VerticalSync()
        )

    # option access, `None` and empty text mean "not set"; 0/False are set
    def _text(self, key: str, default: str) -> str:
        value = self.options.get(key)
        return str(value) if value else default

    def _number(self, key: str, default: int) -> int:
        value = self.options.get(key)
        return default if value is None or value == "" else int(value)

    def _flag(self, key: str) -> bool:
        return bool(self.options.get(key))

    def solve(
        self, clip: ClipInfo, rename_index: int
    ) -> Optional[ShotSolution]:
        """Solve one clip.

        Args:
            clip: The clip as read by the host.
            rename_index: Position of the clip in the creator run (0 for
                the first), the step of the shot counter.

        Returns:
            The solution; None when the clip is skipped (its track is
            only a reviewable source, not the driving layer). A skipped
            clip is still registered as a hero.

        Raises:
            ValueError: Unknown hierarchy token, or `useShotName` on a
                clip with an empty shot name.
        """
        options = self.options
        track_name = (
            str(clip.track_name)
            .replace(" ", "_")
            .replace("*", f"noname{clip.track_index}")
        )
        clip_name = str(clip.name)
        default_data = {
            "_folder_": "shots",
            "_sequence_": self.sequence_name,
            "_track_": track_name,
            "_clip_": clip_name,
            "_trackIndex_": clip.track_index,
            "_clipIndex_": clip.index,
        }

        rename = self._flag("clipRename")
        use_shot_name = (
            self._flag("useShotName") and clip.shot_name is not None
        )
        template_name = self._text("clipName", CLIP_NAME_DEFAULT)
        hierarchy = self._text("hierarchy", HIERARCHY_DEFAULT)
        index_from_segment = (
            self._flag("segmentIndex") and clip.shot_name is not None
        )
        count_from = self._number("countFrom", COUNT_DEFAULT)
        count_steps = self._number("countSteps", COUNT_DEFAULT)
        base_variant = self._text("clipVariant", VARIANT_DEFAULT)
        product_type = self._text("plate_product_type", "plate")
        vertical_sync = self._flag("vSyncOn")
        driving_layer = self._text("vSyncTrack", "").replace(" ", "_")
        # `reviewTrack` is the old name of `reviewableSource`
        review_source = (
            options.get("reviewableSource")
            or options.get("reviewTrack")
            or None
        )

        hierarchy_data = {
            key: self._text(key, HIERARCHY_DATA_DEFAULTS[key])
            for key in HIERARCHY_KEYS
        }

        variant = (
            track_name if base_variant == VARIANT_DEFAULT else base_variant
        )
        product_name = f"{product_type}{variant.capitalize()}"

        hero_track = not (vertical_sync and track_name != driving_layer)

        # shot counter
        if index_from_segment:
            shot_num = count_steps * clip.index
        else:
            shot_num = count_from + count_steps * rename_index

        data: Dict[str, Any] = {}
        for key in DATA_KEYS:
            if key in options:
                data[key] = deepcopy(options[key])
        if review_source:
            data["reviewableSource"] = review_source

        # `#` runs are the shot counter, padded to the run length
        formatting = dict(default_data)
        formatting["shot"] = shot_num
        formatted: Dict[str, str] = {}
        for key, value in hierarchy_data.items():
            value = _HASHES.sub(
                lambda m: "{shot:0>%d}" % len(m.group(0)), value)
            formatted[key] = _fmt(value, formatting, f"{key} option")
            data[key] = formatted[key]

        fill_data = dict(default_data)
        fill_data.update(formatted)
        new_clip_name = _fmt(template_name, fill_data, "clipName")
        hierarchy_filled = _fmt(hierarchy, fill_data, "hierarchy")
        formatted.pop("shot")

        instance_data: Dict[str, Any] = {
            "newClipName": new_clip_name,
            "hierarchy": hierarchy_filled,
            "parents": self._parents(hierarchy, hierarchy_data, default_data),
            "hierarchyData": formatted,
            "productName": product_name,
            "productType": product_type,
            "productBaseType": "plate",
            "variant": variant,
            "heroTrack": True,
        }
        if hero_track and vertical_sync:
            self.vertical_sync.register_hero(
                clip.timeline_in, clip.timeline_out, instance_data)
        if not hero_track:
            hero_data = self.vertical_sync.distribute(
                clip.timeline_in,
                clip.timeline_out,
                product_name,
                variant,
                clip.track_index,
                rename_index,
            )
            if hero_data is not None:
                instance_data = hero_data

        data.update(instance_data)
        data["uuid"] = str(uuid.uuid4())

        reviewable = review_source or ""
        if reviewable == REGEX_SOURCE:
            # a review track is searched for each clip; no review switch
            data["reviewableSource"] = self._review_track_from_regex(
                clip.track_name, data.get("reviewTrackRegexPattern", ""))
            data.pop("reviewTrackRegexPattern", None)
        elif reviewable:
            if vertical_sync and not hero_track:
                data.pop("review", None)
                data.pop("reviewableSource", None)
            else:
                data["review"] = True
                data["reviewableSource"] = reviewable
        # `reviewTrack` is set by the hosts' plate collectors at publish,
        # from the creator attributes; the creator does not store it.

        # a track that is only a reviewable source gets no data of its own
        review_track = reviewable.replace(" ", "_")
        if (
            reviewable != REGEX_SOURCE
            and track_name == review_track
            and driving_layer != review_track
        ):
            log.debug(
                "Skip clip %r on track %r: reviewable source, not the "
                "driving layer", clip.name, track_name)
            return None

        # a follower carries the name of its hero
        new_clip_name = data.pop("newClipName")
        renamed: Optional[str] = None
        if rename and not use_shot_name:
            renamed = new_clip_name
            folder_name = new_clip_name
        elif use_shot_name:
            if not clip.shot_name:
                raise ValueError(
                    f"Shot name is not set on clip: {clip.name}")
            folder_name = str(clip.shot_name)
            data["hierarchyData"]["shot"] = folder_name
        else:
            folder_name = clip_name
            data["hierarchyData"]["shot"] = folder_name
        data["folderName"] = folder_name
        data["folderPath"] = f"/{data['hierarchy']}/{folder_name}"
        return ShotSolution(new_clip_name=renamed, data=data)

    def _review_track_from_regex(
        self, track_name: str, pattern: str
    ) -> Optional[str]:
        """First video track whose name matches the pattern, else None.

        `<track_name>` in the pattern is the clip's own track name.
        """
        resolved = str(pattern).replace("<track_name>", track_name)
        try:
            for name in self.video_track_names:
                if re.search(resolved, name):
                    return name
        except re.error as exc:
            log.warning(
                "Invalid review track regex pattern %r: %s", pattern, exc)
        return None

    def _parents(
        self,
        hierarchy: str,
        hierarchy_data: Mapping[str, str],
        default_data: Mapping[str, Any],
    ) -> List[Dict[str, str]]:
        """One parent entity per segment of the hierarchy template."""
        formatting = dict(default_data)
        for key, value in hierarchy_data.items():
            formatting[key] = _fmt(value, default_data, f"{key} option")
        parents = []
        for template in hierarchy.split("/"):
            tokens = _PARENT_TOKEN.findall(template)
            token = tokens[-1].strip("_") if tokens else "folder"
            folder_type = FOLDER_TYPES.get(token)
            if not folder_type:
                raise ValueError(
                    f"Missing folder type for `{token}`. "
                    f"Valid types are: {list(FOLDER_TYPES)}"
                )
            parents.append({
                "entity_type": folder_type,
                "folder_type": folder_type,
                "entity_name": _fmt(template, formatting, "hierarchy"),
            })
        return parents
