"""Image sequence path notations and their normalisation.

Replaces the copies of `get_reformated_path` / `get_padding_from_path` in
`ayon_hiero/api/otio/utils.py`, `ayon_resolve/otio/utils.py` and
`ayon_resolve/api/lib.py`, `get_reformatted_filename`,
`get_padding_from_filename` and `get_frame_from_filename` in
`ayon_flame/otio/utils.py` and `ayon_flame/api/lib.py`, and Hiero's
`get_sequence_pattern_and_padding`.

Notations of an image sequence in a path:

| Notation | Example | Used by |
| --- | --- | --- |
| `printf` | `plate.%04d.exr`, `plate.%d.exr` | Hiero |
| `bracket` | `plate.[0001-1008].exr` | Resolve |
| `hash` | `plate.####.exr` | Hiero, Traypublisher CSV |
| `frame` | `plate.1001.exr` (one concrete frame) | Flame |

The first three name a sequence by their pattern. `frame` is a single file
of a sequence and is only looked for when asked for: a movie called
`clip_0010.mov` must not be read as frame 10.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional, Union

__all__ = (
    "NOTATION_BRACKET",
    "NOTATION_FRAME",
    "NOTATION_HASH",
    "NOTATION_PRINTF",
    "SequencePattern",
    "get_frame",
    "get_padding",
    "parse_sequence_path",
    "reformat_frame_filename",
    "reformat_path",
)

NOTATION_PRINTF = "printf"
NOTATION_BRACKET = "bracket"
NOTATION_HASH = "hash"
NOTATION_FRAME = "frame"

_PRINTF_RE = re.compile(r"%(\d*)d")
_BRACKET_RE = re.compile(r"\[(\d+)-(\d+)\]")
# A run of `#` that is not part of a word: `plate.####.exr` and
# `plate_####.exr`, not the `#1` of `Shot #1 final.mov`.
_HASH_RE = re.compile(r"(?<![A-Za-z0-9#])#+(?![A-Za-z0-9#])")
# Digits after a separator (`.`, `_`, `-`, a space) and right before the
# file extension.
_FRAME_RE = re.compile(r"[^A-Za-z0-9/\\](\d+)(?=\.[^./\\]*$)")


@dataclass(frozen=True)
class SequencePattern:
    """A sequence notation found in a path.

    Attributes:
        head: Path text before the notation.
        tail: Path text after it.
        notation: One of the `NOTATION_*` names.
        padding: Digits of the frame number, None when unknown (`%d`).
        first_frame: First frame as written, `bracket` notation only.
        last_frame: Last frame as written, `bracket` notation only.
    """

    head: str
    tail: str
    notation: str
    padding: Optional[int] = None
    first_frame: Optional[str] = None
    last_frame: Optional[str] = None

    def format_printf(self, padded: bool = True) -> str:
        """Render the path with a printf frame token.

        Args:
            padded: `%04d` when True and the padding is known, else `%d`.
        """
        return self.head + _printf_token(self.padding, padded) + self.tail


def _printf_token(padding: Optional[int], padded: bool) -> str:
    if padded and padding:
        return "%0{}d".format(padding)
    return "%d"


def _last_match(pattern: re.Pattern, text: str):
    match = None
    for match in pattern.finditer(text):
        pass
    return match


def parse_sequence_path(
    path: str, allow_frame_numbers: bool = False
) -> Optional[SequencePattern]:
    """Find the sequence notation in a path or file name.

    The notation closest to the end of the path wins, so folders with
    brackets or hashes do not matter: in
    `/shots/[010-020]/plate.####.exr` the hashes win.

    Args:
        path: Path, URL or file name.
        allow_frame_numbers: Also read a concrete frame number before the
            extension (`plate.1001.exr`) as a sequence.

    Returns:
        Optional[SequencePattern]: The notation, None for a plain file.
    """
    found = []
    for notation, regex in (
        (NOTATION_PRINTF, _PRINTF_RE),
        (NOTATION_BRACKET, _BRACKET_RE),
        (NOTATION_HASH, _HASH_RE),
    ):
        match = _last_match(regex, path)
        if match:
            found.append((match.start(), notation, match))
    if found:
        _, notation, match = max(found, key=lambda item: item[0])
        head, tail = path[:match.start()], path[match.end():]
        if notation == NOTATION_PRINTF:
            digits = match.group(1)
            return SequencePattern(
                head, tail, notation, int(digits) if digits else None
            )
        if notation == NOTATION_BRACKET:
            first, last = match.group(1), match.group(2)
            return SequencePattern(
                head, tail, notation, len(first), first, last
            )
        return SequencePattern(head, tail, notation, len(match.group(0)))

    if allow_frame_numbers:
        match = _last_match(_FRAME_RE, path)
        if match:
            frame = match.group(1)
            return SequencePattern(
                path[:match.start(1)],
                path[match.end(1):],
                NOTATION_FRAME,
                len(frame),
                frame,
                frame,
            )
    return None


def get_padding(
    path: str, allow_frame_numbers: bool = False
) -> Optional[int]:
    """Get the frame padding of a sequence path.

    Example:
        get_padding("plate.[0001-1008].exr") > 4
        get_padding("plate.####.exr") > 4
        get_padding("plate.%d.exr") > None

    Args:
        path: Path, URL or file name.
        allow_frame_numbers: Also read `plate.0001.exr` (see
            `parse_sequence_path`).

    Returns:
        Optional[int]: Padding, None for a plain file or an unpadded
            `%d` token.
    """
    pattern = parse_sequence_path(path, allow_frame_numbers)
    return pattern.padding if pattern else None


def get_frame(
    filename: str,
    extensions: Optional[Union[str, Iterable[str]]] = None,
) -> Optional[str]:
    """Get the frame number text of one file of a sequence.

    Example:
        get_frame("plate.0001.exr") > "0001"

    Args:
        filename: File name or path of a single frame.
        extensions: Extensions with the dot (such as ayon-core
            `IMAGE_EXTENSIONS`), a single one may be a str; compared
            without regard to case. Any extension when None.

    Returns:
        Optional[str]: The digits as written, None when there are none or
            the extension is not accepted.
    """
    if extensions is not None:
        if isinstance(extensions, str):
            extensions = (extensions,)
        dot = filename.rfind(".")
        ext = filename[dot:].lower() if dot != -1 else ""
        if ext not in {item.lower() for item in extensions}:
            return None
    match = _last_match(_FRAME_RE, filename)
    return match.group(1) if match else None


def reformat_path(
    path: str, padded: bool = True, first: bool = False
) -> str:
    """Rewrite a `printf`, `bracket` or `hash` sequence path as printf.

    A plain path, and a concrete frame such as `plate.1001.exr`, are
    returned unchanged. Use `reformat_frame_filename` for the latter.

    Example:
        reformat_path("plate.[0001-1008].exr") > "plate.%04d.exr"
        reformat_path("plate.[0001-1008].exr", padded=False) >
            "plate.%d.exr"
        reformat_path("plate.[0001-1008].exr", padded=False, first=True) >
            "plate.0001.exr"

    Args:
        path: Path, URL or file name.
        padded: Keep the padding: `%04d` instead of `%d`.
        first: Replace a `bracket` range by its first frame. It only
            applies when not `padded`: `padded=True` (the default, as in
            `ayon_resolve/otio/utils.py`) wins. The caller in
            `ayon_resolve/api/lib.py` relied on a default of
            `padded=False`, so it must pass `padded=False, first=True`.
    """
    pattern = parse_sequence_path(path)
    if pattern is None:
        return path
    if (
        not (padded and pattern.padding)
        and first
        and pattern.first_frame is not None
    ):
        return pattern.head + pattern.first_frame + pattern.tail
    return pattern.format_printf(padded)


def reformat_frame_filename(filename: str, padded: bool = True) -> str:
    """Rewrite the frame number of one file as a printf token.

    Example:
        reformat_frame_filename("plate.1001.exr") > "plate.%04d.exr"

    Args:
        filename: File name or path of a single frame.
        padded: `%04d` when True, else `%d`.

    Returns:
        str: The rewritten name, the input when it has no frame number.
    """
    pattern = parse_sequence_path(filename, allow_frame_numbers=True)
    if pattern is None or pattern.notation != NOTATION_FRAME:
        return filename
    return pattern.format_printf(padded)
