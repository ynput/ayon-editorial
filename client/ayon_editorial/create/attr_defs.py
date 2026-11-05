"""Attribute specs (`shots/options.py`) as `ayon_core` definitions.

Replaces the attribute definition code of the Hiero and Flame
`CreateShotClip` and of their shot, plate and audio instance creators.
No logic lives here: what is shown, which defaults and items apply is
decided in `shots/options.py`.
"""
from __future__ import annotations

import logging
from typing import Any, Collection, List, Mapping, Optional, Sequence

from ayon_core.lib import BoolDef, EnumDef, NumberDef, TextDef, UILabelDef

from ..shots.options import (
    AUDIO_INSTANCE_ATTRIBUTES,
    CLIP_CREATOR_ATTRIBUTES,
    PLATE_INSTANCE_ATTRIBUTES,
    SHOT_INSTANCE_ATTRIBUTES,
    AttributeSpec,
    attribute_default,
    attribute_items,
)

__all__ = [
    "build_attr_def",
    "get_audio_attr_defs",
    "get_plate_attr_defs",
    "get_pre_create_attr_defs",
    "get_shot_attr_defs",
]

log = logging.getLogger(__name__)


def _header(text: str) -> str:
    return f"<br><b>{text}</b>"


def build_attr_def(
    spec: AttributeSpec,
    default: Any = None,
    items: Optional[Sequence[Mapping[str, Any]]] = None,
    disabled: Optional[bool] = None,
):
    """Create the `ayon_core` definition of one spec.

    Args:
        spec: Attribute spec.
        default: Default value.
        items: Enum items as `{"value", "label"}` dicts.
        disabled: Overrides `spec.disabled`.

    Returns:
        An attribute definition.
    """
    if disabled is None:
        disabled = spec.disabled
    common = {"label": spec.label, "tooltip": spec.tooltip or None}
    if spec.kind == "label":
        return UILabelDef(label=_header(spec.label))
    if spec.kind == "bool":
        return BoolDef(
            spec.key, default=default, disabled=disabled, **common)
    if spec.kind == "text":
        return TextDef(
            spec.key, default=default, disabled=disabled, **common)
    if spec.kind == "number":
        return NumberDef(
            spec.key, default=default, disabled=disabled, **common)
    if spec.kind == "enum":
        return EnumDef(
            spec.key, items=list(items or []), default=default,
            disabled=disabled, **common)
    raise ValueError(f"Unknown attribute kind: {spec.kind!r}")


def get_pre_create_attr_defs(
    presets: Mapping[str, Any],
    track_names: Sequence[str],
    hidden: Collection[str],
    host_name: str = "",
) -> List[Any]:
    """Definitions of the clip creator's pre-create attributes.

    Args:
        presets: Matched profile (`get_clip_creator_presets`).
        track_names: Video track names of the current timeline.
        hidden: Keys not shown (`get_hidden_attributes`). A section
            header is dropped when all its attributes are hidden.
        host_name: Host name, to drop items other hosts cannot serve.

    Returns:
        Definitions in display order.
    """
    visible = [
        spec for spec in CLIP_CREATOR_ATTRIBUTES
        if spec.kind != "label" and spec.key not in hidden
    ]
    sections = {spec.section for spec in visible if spec.section}
    attr_defs: List[Any] = []
    for spec in CLIP_CREATOR_ATTRIBUTES:
        if spec.kind == "label":
            if spec.section in sections:
                attr_defs.append(build_attr_def(spec))
            continue
        if spec.key in hidden:
            continue
        items = None
        if spec.kind == "enum":
            items = attribute_items(spec, presets, track_names, host_name)
        attr_defs.append(
            build_attr_def(spec, attribute_default(spec, presets), items)
        )
    return attr_defs


def get_shot_attr_defs(host_name: str = "") -> List[Any]:
    """Definitions of the shot instance's creator attributes."""
    return _instance_attr_defs(SHOT_INSTANCE_ATTRIBUTES, host_name)


def get_plate_attr_defs(
    track_names: Sequence[str] = (),
    review: bool = False,
    parent_instance: Optional[str] = None,
    host_name: str = "",
) -> List[Any]:
    """Definitions of the plate instance's creator attributes.

    Args:
        track_names: Video track names for `reviewableSource`.
        review: Current value of `review`; `reviewableSource` is enabled
            only while it is on.
        parent_instance: Label of the linked shot instance.
        host_name: Host name; `publish_effects` is Hiero only.
    """
    return _instance_attr_defs(
        PLATE_INSTANCE_ATTRIBUTES, host_name, track_names, review,
        parent_instance,
    )


def get_audio_attr_defs(
    parent_instance: Optional[str] = None, host_name: str = ""
) -> List[Any]:
    """Definitions of the audio instance's creator attributes."""
    return _instance_attr_defs(
        AUDIO_INSTANCE_ATTRIBUTES, host_name,
        parent_instance=parent_instance,
    )


def _instance_attr_defs(
    specs: Sequence[AttributeSpec],
    host_name: str,
    track_names: Sequence[str] = (),
    review: bool = False,
    parent_instance: Optional[str] = None,
) -> List[Any]:
    attr_defs: List[Any] = []
    for spec in specs:
        if spec.hosts is not None and host_name not in spec.hosts:
            continue
        default = spec.default
        disabled = spec.disabled
        items = None
        if spec.key == "parentInstance":
            default = parent_instance
        elif spec.key == "reviewableSource":
            disabled = not review
        if spec.kind == "enum":
            items = attribute_items(spec, None, track_names, host_name)
        attr_defs.append(build_attr_def(spec, default, items, disabled))
    return attr_defs
