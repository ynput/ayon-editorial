"""What a host reads from one timeline clip, as plain data."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ClipInfo:
    """One timeline clip (Hiero track item, Flame segment).

    The host adapter fills it; the shared code never sees host objects.

    Attributes:
        uid: Unique id of the clip in the workfile (Hiero `guid()`,
            Flame marker `clip_index`), used to find the clip again.
        name: Clip name.
        index: Clip index on its track (Hiero `eventNumber()`, Flame
            segment index), the `_clipIndex_` token.
        track_name: Name of the clip's track.
        track_index: Index of the clip's track, the `_trackIndex_` token.
        sequence_name: Name of the sequence (timeline).
        timeline_in: First record frame.
        timeline_out: Last record frame, inclusive.
        source_in: First source frame.
        source_out: Last source frame, inclusive.
        shot_name: Shot name the host keeps on the clip (Flame); None
            where the host has none.
    """

    uid: str
    name: str
    index: int
    track_name: str
    track_index: int
    sequence_name: str
    timeline_in: int
    timeline_out: int
    source_in: float
    source_out: float
    shot_name: Optional[str] = None

    @property
    def duration(self) -> int:
        """Record duration in frames."""
        return self.timeline_out - self.timeline_in + 1
