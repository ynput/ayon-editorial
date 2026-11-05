"""Clip creator attribute schema, profile lookup and hidden values.

Replaces the pre-create attribute lists of the Hiero and Flame
`CreateShotClip` creators, the `CLIP_ATTR_DEFS` lists of their shot
instance creators, and Flame's `overridable_attributes` filter. The schema
is plain data; `create/attr_defs.py` turns it into `ayon_core` definitions.

Profiles come from `project_settings["editorial"]["create"]
["CreateShotClip"]["profiles"]` and are matched by host name and task type
with the rules of `ayon_core.lib.filter_profiles` (regex full match, `*`
or an empty list matches all, the most specific profile wins, the first
one on a tie).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import (
    Any,
    Collection,
    Dict,
    FrozenSet,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
)

__all__ = [
    "ALL_OVERRIDES",
    "AUDIO_INSTANCE_ATTRIBUTES",
    "AttributeSpec",
    "CLIP_CREATOR_ATTRIBUTES",
    "PLATE_INSTANCE_ATTRIBUTES",
    "PROFILE_DEFAULTS",
    "SHOT_INSTANCE_ATTRIBUTES",
    "TRACK_ENUM_KEYS",
    "attribute_default",
    "attribute_items",
    "fill_hidden_values",
    "filter_profiles",
    "get_clip_creator_presets",
    "get_hidden_attributes",
    "supported_attribute_keys",
]

log = logging.getLogger(__name__)

HIERO = "hiero"
FLAME = "flame"

Item = Tuple[Any, str]


@dataclass(frozen=True)
class AttributeSpec:
    """One creator attribute as data.

    Attributes:
        key: Attribute key (also the key in the profile when it has one).
        kind: `bool`, `text`, `number`, `enum` or `label` (a UI header).
        label: Label shown to the artist.
        tooltip: Tooltip.
        default: Default when the profile has no value for `key`.
        items: Fixed enum items as (value, label) pairs. Enums without
            items take them from the profile or from track names.
        hosts: Hosts that support the attribute; None means all.
        section: Section header the attribute belongs to.
        disabled: Shown but not editable.
    """

    key: str
    kind: str
    label: str
    tooltip: str = ""
    default: Any = None
    items: Optional[Tuple[Item, ...]] = None
    hosts: Optional[FrozenSet[str]] = None
    section: str = ""
    disabled: bool = False


# Enum keys whose items end with the host's video track names.
TRACK_ENUM_KEYS = frozenset({"vSyncTrack", "reviewableSource"})

# Enum items only some hosts can serve: (key, value) -> hosts.
_ITEM_HOSTS: Dict[Tuple[str, Any], FrozenSet[str]] = {
    ("reviewableSource", "review_track_regex_pattern"): frozenset({HIERO}),
}

_NO_TRACKS = (None, "<nothing to select>")

_TOKENS_HELP = (
    "\nUsable tokens:\n"
    "    {_clip_}: name of used clip\n"
    "    {_track_}: name of parent track layer\n"
    "    {_sequence_}: name of parent sequence (timeline)"
)

_S_HIERARCHY = "Shot Hierarchy And Rename Settings"
_S_TEMPLATE = "Shot Template Keywords"
_S_VSYNC = "Vertical Synchronization Of Attributes"
_S_PUBLISH = "Publish Settings"
_S_SHOT = "Shot Attributes"

_FLAME_ONLY = frozenset({FLAME})
_HIERO_ONLY = frozenset({HIERO})


def _label(section: str) -> AttributeSpec:
    return AttributeSpec(
        key="section:" + section, kind="label", label=section,
        section=section,
    )


def _text(key, label, tooltip, section, **kwargs) -> AttributeSpec:
    return AttributeSpec(
        key, "text", label, tooltip, section=section, **kwargs)


def _bool(key, label, tooltip, section, **kwargs) -> AttributeSpec:
    return AttributeSpec(
        key, "bool", label, tooltip, section=section, **kwargs)


def _number(key, label, tooltip, section, **kwargs) -> AttributeSpec:
    return AttributeSpec(
        key, "number", label, tooltip, section=section, **kwargs)


# Union of the pre-create attributes of both hosts, in display order.
# Defaults come from the profile (`attribute_default`).
CLIP_CREATOR_ATTRIBUTES: Tuple[AttributeSpec, ...] = (
    AttributeSpec(
        "use_selection", "bool", "Use only selected clip(s).",
        "When enabled it restricts create process to selected clips.",
        default=True,
    ),
    _label(_S_HIERARCHY),
    _text(
        "hierarchy", "Shot Parent Hierarchy",
        "Parents folder for shot root folder, "
        "Template filled with *Hierarchy Data* section",
        _S_HIERARCHY,
    ),
    _bool(
        "useShotName", "Use shot name",
        "Use name form Shot name clip attribute.",
        _S_HIERARCHY, hosts=_FLAME_ONLY,
    ),
    _bool(
        "clipRename", "Rename clips", "Renaming selected clips on fly",
        _S_HIERARCHY,
    ),
    _text(
        "clipName", "Clip Name Template",
        "template for creating shot names, used for "
        "renaming (use rename: on)",
        _S_HIERARCHY,
    ),
    _bool(
        "segmentIndex", "Segment Index",
        "Take number from segment index",
        _S_HIERARCHY, hosts=_FLAME_ONLY,
    ),
    _number(
        "countFrom", "Count sequence from",
        "Set where the sequence number starts from", _S_HIERARCHY,
    ),
    _number(
        "countSteps", "Stepping number",
        "What number is adding every new step", _S_HIERARCHY,
    ),
    _label(_S_TEMPLATE),
    _text(
        "folder", "{folder}",
        "Name of folder used for root of generated shots.\n"
        + _TOKENS_HELP,
        _S_TEMPLATE,
    ),
    _text(
        "episode", "{episode}", "Name of episode.\n" + _TOKENS_HELP,
        _S_TEMPLATE,
    ),
    _text(
        "sequence", "{sequence}",
        "Name of sequence of shots.\n" + _TOKENS_HELP, _S_TEMPLATE,
    ),
    _text(
        "track", "{track}", "Name of timeline track.\n" + _TOKENS_HELP,
        _S_TEMPLATE,
    ),
    _text(
        "shot", "{shot}",
        "Name of shot. '#' is converted to padded number.\n"
        + _TOKENS_HELP,
        _S_TEMPLATE,
    ),
    _label(_S_VSYNC),
    _bool(
        "vSyncOn", "Enable Vertical Sync",
        "Switch on if you want clips above each other to share its "
        "attributes",
        _S_VSYNC,
    ),
    AttributeSpec(
        "vSyncTrack", "enum", "Hero track",
        "Select driving track name which should be mastering all others",
        section=_S_VSYNC,
    ),
    _label(_S_PUBLISH),
    AttributeSpec(
        "clipVariant", "enum", "Product Variant",
        "Chose variant which will be then used for product name, if "
        "<track_name> is selected, name of track layer will be used",
        section=_S_PUBLISH,
    ),
    AttributeSpec(
        "plate_product_type", "enum", "Plate Product Type",
        "How the product will be used", section=_S_PUBLISH,
    ),
    AttributeSpec(
        "reviewableSource", "enum", "Reviewable Source",
        "Generate preview videos on fly, if '< none >' is defined "
        "nothing will be generated.",
        items=(
            (None, "< none >"),
            ("clip_media", "[ Clip's media ]"),
            ("review_track_regex_pattern",
             "[ Review track regex pattern ]"),
        ),
        section=_S_PUBLISH,
    ),
    _text(
        "reviewTrackRegexPattern", "Review track regex pattern",
        "Attempt to match track names against this regex pattern.",
        _S_PUBLISH, hosts=_HIERO_ONLY, default="<track_name>_ref",
    ),
    _bool(
        "export_audio", "Include audio",
        "Process products with corresponding audio", _S_PUBLISH,
    ),
    _bool(
        "sourceResolution", "Source resolution",
        "Is resolution taken from timeline or source?", _S_PUBLISH,
    ),
    _label(_S_SHOT),
    _number(
        "workfileFrameStart", "Workfiles Start Frame",
        "Set workfile starting frame number", _S_SHOT,
    ),
    _number(
        "handleStart", "Handle start (head)", "Handle at start of clip",
        _S_SHOT,
    ),
    _number(
        "handleEnd", "Handle end (tail)", "Handle at end of clip",
        _S_SHOT,
    ),
    _bool(
        "includeHandles", "Include handles",
        "Should the handles be included?", _S_SHOT,
    ),
    _bool(
        "retimedHandles", "Retimed handles",
        "Should the handles be retimed?", _S_SHOT,
    ),
    _bool(
        "retimedFramerange", "Retimed framerange",
        "Should the framerange be retimed?", _S_SHOT,
    ),
)

_FPS_ITEMS: Tuple[Item, ...] = (
    ("from_selection", "From selection"),
    # Flame stored 23.997 here, a typo of its own label.
    (23.976, "23.976"),
    (24, "24"),
    (25, "25"),
    (29.97, "29.97"),
    (30, "30"),
)


def _readonly(key: str, label: str) -> AttributeSpec:
    return AttributeSpec(
        key, "number", label, default=0, disabled=True)


# Union of both hosts' shot instance attributes (`CLIP_ATTR_DEFS` plus
# `useSourceResolution`). Hiero gains the three retime flags.
SHOT_INSTANCE_ATTRIBUTES: Tuple[AttributeSpec, ...] = (
    AttributeSpec(
        "fps", "enum", "FPS", default="from_selection", items=_FPS_ITEMS,
    ),
    AttributeSpec(
        "workfileFrameStart", "number", "Workfile start frame",
        default=1001,
    ),
    AttributeSpec("handleStart", "number", "Handle start", default=0),
    AttributeSpec("handleEnd", "number", "Handle end", default=0),
    _readonly("frameStart", "Frame start"),
    _readonly("frameEnd", "Frame end"),
    _readonly("clipIn", "Clip in"),
    _readonly("clipOut", "Clip out"),
    _readonly("clipDuration", "Clip duration"),
    _readonly("sourceIn", "Media source in"),
    _readonly("sourceOut", "Media source out"),
    AttributeSpec(
        "includeHandles", "bool", "Include handles", default=False,
    ),
    AttributeSpec(
        "retimedHandles", "bool", "Retimed handles", default=True,
    ),
    AttributeSpec(
        "retimedFramerange", "bool", "Retimed framerange", default=True,
    ),
    AttributeSpec(
        "useSourceResolution", "bool", "Set shot resolution from plate",
        "Is resolution taken from timeline or source?", default=False,
    ),
)

_PARENT_INSTANCE = AttributeSpec(
    "parentInstance", "text", "Linked to", default=None, disabled=True,
)
_REVIEW = AttributeSpec(
    "review", "bool", "Review", "Switch to reviewable instance",
    default=False,
)

# `reviewableSource` is disabled until `review` is on; the creator mixin
# flips it. Its items are these plus the video track names.
PLATE_INSTANCE_ATTRIBUTES: Tuple[AttributeSpec, ...] = (
    _PARENT_INSTANCE,
    _REVIEW,
    AttributeSpec(
        "reviewableSource", "enum", "Reviewable Source",
        "Selecting source for reviewable files.",
        items=(("clip_media", "[ Clip's media ]"),),
        disabled=True,
    ),
    AttributeSpec(
        "publish_effects", "enum", "Publish clip effects",
        "Discover and publish clip effects",
        items=(
            ("ignore_effects", "Ignore Effects"),
            ("publish_effects", "Publish Effects"),
            ("publish_only_effects", "Publish Only Effects"),
        ),
        hosts=_HIERO_ONLY,
    ),
)

# Flame's audio instance had no `review` toggle although its creator sets
# it; the unified set shows it for both hosts.
AUDIO_INSTANCE_ATTRIBUTES: Tuple[AttributeSpec, ...] = (
    _PARENT_INSTANCE,
    _REVIEW,
)

# Attributes a profile may leave to the artist: the server's overrides
# enum (`clip_creator_overrides_enum`) plus the hero track.
ALL_OVERRIDES: Tuple[str, ...] = (
    "hierarchy", "useShotName", "clipRename", "clipName", "segmentIndex",
    "countFrom", "countSteps", "folder", "episode", "sequence", "track",
    "shot", "vSyncOn", "clipVariant", "plate_product_type",
    "reviewableSource", "export_audio", "sourceResolution",
    "workfileFrameStart", "handleStart", "handleEnd", "includeHandles",
    "retimedHandles", "retimedFramerange",
)
_OVERRIDABLE = frozenset(ALL_OVERRIDES) | {"vSyncTrack"}

# Values of a profile without a match: the defaults of the server model
# `ClipCreatorProfile` (tests compare them).
PROFILE_DEFAULTS: Dict[str, Any] = {
    "host_names": [],
    "task_types": [],
    "overrides": list(ALL_OVERRIDES),
    "hierarchy": "{folder}/{sequence}",
    "useShotName": False,
    "clipRename": True,
    "clipName": "{track}{sequence}{shot}",
    "segmentIndex": False,
    "countFrom": 10,
    "countSteps": 10,
    "folder": "shots",
    "episode": "ep01",
    "sequence": "sq01",
    "track": "{_track_}",
    "shot": "sh###",
    "vSyncOn": False,
    "clip_variants": ["<track_name>", "main", "bg", "fg", "animatic"],
    "plate_product_types": [],
    "reviewTrackRegexPattern": "<track_name>_ref",
    "export_audio": False,
    "sourceResolution": False,
    "workfileFrameStart": 1001,
    "handleStart": 10,
    "handleEnd": 10,
    "includeHandles": False,
    "retimedHandles": True,
    "retimedFramerange": True,
}


def _validate_by_regexes(value: Optional[str], patterns: Any) -> int:
    """Score one filter: 0 no filter, 1 match, -1 no match."""
    if not patterns:
        return 0
    if not isinstance(patterns, (list, tuple, set)):
        patterns = [patterns]
    if "*" in patterns:
        return 0
    if not value:
        return -1
    for pattern in patterns:
        if not pattern:
            continue
        try:
            if re.fullmatch(pattern, value):
                return 1
        except (TypeError, re.error):
            log.warning("Invalid profile filter: %r", pattern)
    return -1


def filter_profiles(
    profiles: Optional[Sequence[Mapping[str, Any]]],
    host_name: str,
    task_type: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Pick the most specific profile for a host and task type.

    Same rules as `ayon_core.lib.filter_profiles` with the keys
    `host_names` and `task_types`: a profile whose non-empty filter does not
    match is out; each matching filter scores a point; the highest score
    wins; on a tie the profile with a filter on the earlier key wins
    (`host_names` before `task_types`), then the first one in the list.

    Args:
        profiles: Profiles from the settings.
        host_name: Host name, e.g. `hiero`.
        task_type: Task type name, None when unknown.

    Returns:
        The profile, or None when none matches.
    """
    best: List[Tuple[Mapping[str, Any], List[bool]]] = []
    best_points = -1
    for profile in profiles or []:
        points = 0
        scores: List[bool] = []
        for key, value in (
            ("host_names", host_name), ("task_types", task_type)
        ):
            match = _validate_by_regexes(value, profile.get(key))
            if match == -1:
                points = -1
                break
            points += match
            scores.append(bool(match))
        if points < 0 or points < best_points:
            continue
        if points > best_points:
            best, best_points = [], points
        best.append((profile, scores))

    if not best:
        return None
    # Tie: prefer a profile with a filter on the first key, then the next.
    for idx in range(2):
        with_filter = [item for item in best if item[1][idx]]
        if with_filter:
            best = with_filter
        if len(best) == 1:
            break
    return dict(best[0][0])


def get_clip_creator_presets(
    editorial_settings: Mapping[str, Any],
    host_name: str,
    task_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Return the clip creator presets for a host and task type.

    Args:
        editorial_settings: `project_settings["editorial"]`.
        host_name: Host name, e.g. `flame`.
        task_type: Task type name, None when unknown.

    Returns:
        The matched profile on top of `PROFILE_DEFAULTS`; the defaults
        alone when no profile matches.
    """
    create = (editorial_settings or {}).get("create") or {}
    profiles = (create.get("CreateShotClip") or {}).get("profiles") or []
    presets = {
        key: (list(value) if isinstance(value, list) else value)
        for key, value in PROFILE_DEFAULTS.items()
    }
    profile = filter_profiles(profiles, host_name, task_type)
    if profile is None:
        log.debug("No clip creator profile for %s, using defaults", host_name)
    else:
        presets.update(profile)
    return presets


def supported_attribute_keys(host_name: str) -> Set[str]:
    """Keys of the pre-create attributes `host_name` supports."""
    return {
        spec.key
        for spec in CLIP_CREATOR_ATTRIBUTES
        if spec.kind != "label"
        and (spec.hosts is None or host_name in spec.hosts)
    }


def get_hidden_attributes(
    presets: Mapping[str, Any], supported: Collection[str]
) -> Set[str]:
    """Return the pre-create keys the artist does not see.

    An overridable attribute that is not in `presets["overrides"]` is
    hidden (its value comes from the profile). `vSyncTrack` is shown when
    `vSyncOn` is overridable or on in the profile. Keys the host does not
    support are always hidden.

    Args:
        presets: Matched profile (`get_clip_creator_presets`).
        supported: Attribute keys the host supports.

    Returns:
        Hidden attribute keys.
    """
    enabled = set(presets.get("overrides") or [])
    if "vSyncOn" in enabled or presets.get("vSyncOn"):
        enabled.add("vSyncTrack")
    hidden = {key for key in _OVERRIDABLE if key not in enabled}
    hidden.update(
        spec.key
        for spec in CLIP_CREATOR_ATTRIBUTES
        if spec.kind != "label" and spec.key not in supported
    )
    return hidden


def fill_hidden_values(
    pre_create_data: Mapping[str, Any],
    presets: Mapping[str, Any],
    hidden: Collection[str],
) -> Dict[str, Any]:
    """Add the profile value of every hidden attribute.

    `clipVariant` and `plate_product_type` have no key of their own in a
    profile; their first entry in `clip_variants` and
    `plate_product_types` (else `plate`) is used.

    Args:
        pre_create_data: Values the artist set.
        presets: Matched profile.
        hidden: Keys from `get_hidden_attributes`.

    Returns:
        A new dict; the input is not changed.
    """
    data = dict(pre_create_data)
    for key in hidden:
        if key in presets:
            data[key] = presets[key]
    if "clipVariant" in hidden and presets.get("clip_variants"):
        data["clipVariant"] = presets["clip_variants"][0]
    if "plate_product_type" in hidden:
        data["plate_product_type"] = (
            list(presets.get("plate_product_types") or []) or ["plate"]
        )[0]
    return data


def attribute_default(
    spec: AttributeSpec, presets: Optional[Mapping[str, Any]] = None
) -> Any:
    """Default of a pre-create attribute: the profile value, else spec's.

    Enums without a profile key default to None (the first item).
    """
    presets = presets or {}
    if spec.key == "clipVariant":
        variants = presets.get("clip_variants")
        return variants[0] if variants else None
    if spec.key == "plate_product_type":
        types = presets.get("plate_product_types")
        return types[0] if types else "plate"
    if spec.key in presets and spec.key != "overrides":
        return presets[spec.key]
    return spec.default


def attribute_items(
    spec: AttributeSpec,
    presets: Optional[Mapping[str, Any]] = None,
    track_names: Sequence[str] = (),
    host_name: str = "",
) -> List[Dict[str, Any]]:
    """Enum items of `spec` as `{"value", "label"}` dicts.

    Args:
        spec: An enum spec.
        presets: Matched profile, for `clipVariant`/`plate_product_type`.
        track_names: Host video track names.
        host_name: Drops items other hosts cannot serve; empty keeps all.
    """
    presets = presets or {}
    if spec.key == "clipVariant":
        values = list(presets.get("clip_variants") or [])
        pairs: List[Item] = [(value, value) for value in values]
    elif spec.key == "plate_product_type":
        values = list(presets.get("plate_product_types") or []) or ["plate"]
        pairs = [(value, value) for value in values]
    else:
        pairs = [
            pair for pair in (spec.items or ())
            if not host_name
            or host_name in _ITEM_HOSTS.get((spec.key, pair[0]), {host_name})
        ]
    items = [{"value": value, "label": label} for value, label in pairs]
    if spec.key in TRACK_ENUM_KEYS:
        items.extend(
            {"value": name, "label": f"Track: {name}"}
            for name in track_names
        )
        if spec.key == "vSyncTrack" and not track_names:
            items = [{"value": _NO_TRACKS[0], "label": _NO_TRACKS[1]}]
    return items
