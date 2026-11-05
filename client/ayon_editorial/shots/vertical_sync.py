"""Vertical sync: hero clip matching and product name de-duplication.

Replaces the `vertical_clip_match` / `vertical_clip_used` dicts that Hiero
passes into `PublishClip` and the class level dicts of Flame's
`PublishableClip` (`restore_all_caches`). One `VerticalSync` lives for one
creator run; `ShotHierarchySolver` registers the hero clip of every
timeline range and hands the data of a hero to the clips of the other
tracks that sit inside its range.
"""
from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

__all__ = ["VerticalSync"]


class VerticalSync:
    """Per creator run state of the vertical sync.

    Attributes:
        hero_clips: Hero clip data by `(timeline_in, timeline_out)`, in
            registration order. A later hero with the same range replaces
            the data but keeps the position.
        used_names: Product names already given to the follower clips of
            a hero, by `"<newClipName><productName>"` of the hero.
    """

    def __init__(self) -> None:
        self.hero_clips: Dict[Tuple[int, int], Dict[str, Any]] = {}
        self.used_names: Dict[str, List[str]] = {}

    def reset(self) -> None:
        """Forget all hero clips and used names (start of a creator run)."""
        self.hero_clips = {}
        self.used_names = {}

    def register_hero(
        self,
        timeline_in: int,
        timeline_out: int,
        data: Dict[str, Any],
    ) -> None:
        """Remember the data of a hero clip.

        Args:
            timeline_in: First record frame of the hero clip.
            timeline_out: Last record frame of the hero clip.
            data: Shot data of the hero (needs `productName` and
                `newClipName` to be usable by `distribute`). Copied.
        """
        self.hero_clips[(timeline_in, timeline_out)] = deepcopy(data)

    def find_hero(
        self, timeline_in: int, timeline_out: int
    ) -> Optional[Dict[str, Any]]:
        """Find the first hero whose range contains the given range.

        Args:
            timeline_in: First record frame of the follower clip.
            timeline_out: Last record frame of the follower clip.

        Returns:
            The registered hero data (not a copy), None when no hero
            range contains the clip.
        """
        for (hero_in, hero_out), hero_data in self.hero_clips.items():
            if timeline_in < hero_in or timeline_out > hero_out:
                continue
            return hero_data
        return None

    def distribute(
        self,
        timeline_in: int,
        timeline_out: int,
        product_name: str,
        variant: str,
        track_index: int,
        rename_index: int,
    ) -> Optional[Dict[str, Any]]:
        """Give a follower clip the data of the hero that contains it.

        The product name is made unique among the followers of the same
        hero: a name equal to the hero's gets the track index appended; a
        name already used gets the rename index, then the track and rename
        index, then a counter, until it is free. The variant gets the same
        suffix. The chosen name is recorded as used.

        Args:
            timeline_in: First record frame of the follower clip.
            timeline_out: Last record frame of the follower clip.
            product_name: Product name the clip would get on its own.
            variant: Variant the clip would get on its own.
            track_index: Index of the follower's track.
            rename_index: Position of the clip in the creator run.

        Returns:
            A deep copy of the hero data with `heroTrack` False and the
            unique `productName` and `variant`; None when no hero matches.
        """
        hero_data = self.find_hero(timeline_in, timeline_out)
        if hero_data is None:
            return None

        data = deepcopy(hero_data)
        data["heroTrack"] = False

        hero_product = hero_data["productName"]
        used = self.used_names.setdefault(
            f"{hero_data['newClipName']}{hero_product}", []
        )
        suffix = ""
        if product_name == hero_product:
            suffix = str(track_index)
        if f"{product_name}{suffix}" in used:
            base = suffix
            candidates = [
                f"{base}{rename_index}",
                f"{base}{track_index}{rename_index}",
            ]
            counter = 2
            while True:
                if counter > 2:
                    candidates = [f"{base}{rename_index}_{counter}"]
                free = [
                    c for c in candidates
                    if f"{product_name}{c}" not in used
                ]
                if free:
                    suffix = free[0]
                    break
                counter += 1

        name = f"{product_name}{suffix}"
        data["productName"] = name
        data["variant"] = f"{variant}{suffix}"
        used.append(name)
        log.debug("Vertical sync: product name %s (used %s)", name, used)
        return data
