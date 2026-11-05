"""Creator mixins the Hiero and Flame clip creators inherit.

Replaces the shared parts of both hosts' `create_shot_clip.py`: settings
lookup, attribute definitions, hidden values, instance data and the review
toggle. A host combines them with its own creator base:

    class CreateShotClip(ClipCreatorMixin, HieroCreator): ...

The mixins do not subclass `ayon_core` creators and import no host or Qt.
A host keeps its identifiers, selection, `ClipInfo` reading, clip rename
and the metadata I/O.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Mapping, Optional, Set

from ..shots.clip import ClipInfo
from ..shots.instances import build_clip_instances
from ..shots.options import (
    CLIP_CREATOR_ATTRIBUTES,
    fill_hidden_values,
    get_clip_creator_presets,
    get_hidden_attributes,
    supported_attribute_keys,
)
from .attr_defs import (
    get_audio_attr_defs,
    get_pre_create_attr_defs,
    get_plate_attr_defs,
    get_shot_attr_defs,
)

__all__ = [
    "ClipCreatorMixin",
    "ClipInstanceCreatorMixin",
    "ShotInstanceCreatorMixin",
]

log = logging.getLogger(__name__)


class ClipCreatorMixin:
    """The publishable clip creator (`product_base_type` `editorial`).

    Host creators set `host_name` and implement `get_video_track_names`
    and `creator_ids`.

    Attributes:
        host_name: `hiero` or `flame`.
        supported_attributes: Pre-create keys the host supports; None
            takes all of the schema for `host_name`.
        presets: Matched profile, set by `apply_settings`.
    """

    host_name: str = ""
    supported_attributes: Optional[Set[str]] = None
    presets: Dict[str, Any] = {}

    @property
    def creator_ids(self) -> Mapping[str, str]:
        """Identifiers of the host's `shot`, `plate` and `audio` creators."""
        raise NotImplementedError("Host creator must define creator_ids.")

    def get_video_track_names(self) -> List[str]:
        """Video track names of the current timeline."""
        raise NotImplementedError(
            "Host creator must implement get_video_track_names.")

    def apply_settings(self, project_settings: Mapping[str, Any]) -> None:
        """Read the profile of this host and the current task type."""
        super_apply = getattr(super(), "apply_settings", None)
        if super_apply is not None:
            super_apply(project_settings)
        self.presets = get_clip_creator_presets(
            project_settings.get("editorial") or {},
            self.host_name,
            self._get_task_type(),
        )

    def _get_task_type(self) -> Optional[str]:
        """Task type of the current context, None when unavailable."""
        create_context = getattr(self, "create_context", None)
        try:
            task_entity = create_context.get_current_task_entity()
            return (task_entity or {}).get("taskType")
        except Exception:
            log.debug("No current task type available", exc_info=True)
            return None

    def _get_supported(self) -> Set[str]:
        if self.supported_attributes is not None:
            return set(self.supported_attributes)
        return supported_attribute_keys(self.host_name)

    def get_hidden_attributes(self) -> Set[str]:
        """Pre-create keys not shown to the artist."""
        return get_hidden_attributes(self.presets, self._get_supported())

    def get_pre_create_attr_defs(self) -> List[Any]:
        """Pre-create attribute definitions for the current profile."""
        return get_pre_create_attr_defs(
            self.presets,
            self.get_video_track_names(),
            self.get_hidden_attributes(),
            self.host_name,
        )

    def prepare_pre_create_data(
        self, pre_create_data: Mapping[str, Any]
    ) -> Dict[str, Any]:
        """Add the profile values of the hidden attributes.

        Attributes of another host (`useShotName` on Hiero) are dropped,
        so the shot solver never acts on them.
        """
        data = fill_hidden_values(
            pre_create_data, self.presets, self.get_hidden_attributes()
        )
        supported = self._get_supported()
        for spec in CLIP_CREATOR_ATTRIBUTES:
            if spec.kind != "label" and spec.key not in supported:
                data.pop(spec.key, None)
        return data

    def make_clip_instances(
        self,
        clip: ClipInfo,
        solution: Mapping[str, Any],
        pre_create_data: Mapping[str, Any],
    ) -> Dict[str, Dict[str, Any]]:
        """Instance data by creator identifier for one clip.

        Args:
            clip: The clip as the host read it.
            solution: What the shot solver returned for the clip.
            pre_create_data: Output of `prepare_pre_create_data`.
        """
        return build_clip_instances(
            solution, clip, pre_create_data, self.creator_ids
        )


class ShotInstanceCreatorMixin:
    """The hidden shot instance creator."""

    host_name: str = ""

    def get_instance_attr_defs(self) -> List[Any]:
        """Shot creator attribute definitions."""
        return get_shot_attr_defs(self.host_name)


class ClipInstanceCreatorMixin:
    """The hidden plate and audio instance creators.

    Needs `product_base_type`, `create_context` and `identifier` from the
    creator it is combined with. Call `register_callbacks` from the
    creator's own `register_callbacks`.
    """

    host_name: str = ""

    def get_video_track_names(self) -> List[str]:
        """Video track names of the current timeline."""
        raise NotImplementedError(
            "Host creator must implement get_video_track_names.")

    def register_callbacks(self) -> None:
        """Enable `reviewableSource` while `review` is on."""
        self.create_context.add_value_changed_callback(
            self._on_value_change
        )

    def _on_value_change(self, event: Mapping[str, Any]) -> None:
        if self.product_base_type != "plate":
            return
        for item in event["changes"]:
            instance = item["instance"]
            if (
                instance is None
                or instance.creator_identifier != self.identifier
            ):
                continue
            changes = item["changes"].get("creator_attributes", {})
            if "review" not in changes:
                continue
            attr_defs = instance.creator_attributes.attr_defs
            for attr_def in attr_defs:
                if attr_def.key == "reviewableSource":
                    # `disabled` works on old and new ayon-core; Flame
                    # set `enabled` the wrong way round.
                    attr_def.disabled = not changes["review"]
                    break
            instance.set_create_attr_defs(attr_defs)

    def get_attr_defs_for_instance(self, instance) -> List[Any]:
        """Plate or audio attribute definitions of one instance."""
        attributes = instance.creator_attributes
        parent = attributes.get("parentInstance")
        if self.product_base_type == "plate":
            return get_plate_attr_defs(
                self.get_video_track_names(),
                bool(attributes.get("review", False)),
                parent,
                self.host_name,
            )
        return get_audio_attr_defs(parent, self.host_name)
