"""Characterization tests of `otio/paths.py`.

The host functions are copied verbatim below (only renamed per host) and
the shared ones are compared with them. Inputs where a host is wrong are
tested separately and say so.
"""
from __future__ import annotations

import os
import re

import pytest

from ayon_editorial.otio import paths

IMAGE_EXTENSIONS = {".exr", ".dpx", ".png", ".jpg", ".tif"}


# --- Resolve, ayon_resolve/otio/utils.py
def resolve_reformated_path(path, padded=True, first=False):
    num_pattern = r"(\[\d+\-\d+\])"
    padding_pattern = r"(\d+)(?=-)"
    first_frame_pattern = re.compile(r"\[(\d+)\-\d+\]")

    if "[" in path:
        padding = len(re.findall(padding_pattern, path).pop())
        if padded:
            path = re.sub(num_pattern, f"%0{padding}d", path)
        elif first:
            first_frame = re.findall(first_frame_pattern, path, flags=0)
            if len(first_frame) >= 1:
                first_frame = first_frame[0]
            path = re.sub(num_pattern, first_frame, path)
        else:
            path = re.sub(num_pattern, "%d", path)
    return path


def resolve_padding_from_path(path):
    padding_pattern = "(\\d+)(?=-)"
    if "[" in path:
        return len(re.findall(padding_pattern, path).pop())

    return None


# --- Hiero, ayon_hiero/api/otio/utils.py
def hiero_reformated_path(path, padded=True):
    if "%" in path:
        padding_pattern = r"(\d+)"
        padding = int(re.findall(padding_pattern, path).pop())
        num_pattern = r"(%\d+d)"
        if padded:
            path = re.sub(num_pattern, "%0{}d".format(padding), path)
        else:
            path = re.sub(num_pattern, "%d", path)
    return path


# --- Hiero, ayon_hiero/api/lib.py
def hiero_sequence_pattern_and_padding(file):
    foundall = re.findall(
        r"(#+)|(%\d+d)|(?<=[^a-zA-Z0-9])(\d+)(?=\.\w+$)", file)
    if not foundall:
        return None, None
    found = sorted(list(set(foundall[0])))[-1]

    padding = int(
        re.findall(r"\d+", found)[-1]) if "%" in found else len(found)
    return found, padding


# --- Flame, ayon_flame/api/lib.py
FLAME_API_FRAME_PATTERN = re.compile(r"[\._](\d+)[\.]")


def flame_api_reformatted_filename(filename, padded=True):
    found = FLAME_API_FRAME_PATTERN.search(filename)

    if not found:
        return filename

    padding = flame_api_padding_from_filename(filename)

    replacement = "%0{}d".format(padding) if padded else "%d"
    start_idx, end_idx = found.span(1)

    return replacement.join(
        [filename[:start_idx], filename[end_idx:]]
    )


def flame_api_padding_from_filename(filename):
    found = flame_api_frame_from_filename(filename)

    return len(found) if found else None


def flame_api_frame_from_filename(filename):
    found = re.findall(FLAME_API_FRAME_PATTERN, filename)

    return found.pop() if found else None


# --- Flame, ayon_flame/otio/utils.py (the filter on image extensions)
FLAME_OTIO_FRAME_PATTERN = r"[\._](\d+)"


def flame_otio_frame_from_filename(filename):
    _, ext = os.path.splitext(filename)

    if ext.lower() not in IMAGE_EXTENSIONS:
        return None

    pattern = re.compile(FLAME_OTIO_FRAME_PATTERN + re.escape(ext))
    found = pattern.findall(filename)

    return found.pop() if found else None


BRACKET_PATHS = [
    "plate.[0001-1008].exr",
    "plate.[1001-1100].exr",
    "/shots/sh010/plate_v001.[00001-00100].dpx",
    "C:\\proj\\sh010\\plate.[001-100].png",
    "plate.[1-9].exr",
]
PLAIN_PATHS = [
    "plate.mov",
    "/shots/sh010/clip_0010.mov",
    "/shots/sh010/plate.mp4",
    "audio_01.wav",
]
PRINTF_PATHS = [
    "plate.%04d.exr",
    "/shots/sh010/plate.%02d.exr",
    "plate.%08d.dpx",
]


@pytest.mark.parametrize("path", BRACKET_PATHS + PLAIN_PATHS)
@pytest.mark.parametrize("padded", [True, False])
@pytest.mark.parametrize("first", [True, False])
def test_reformat_path_resolve_variant(path, padded, first):
    assert paths.reformat_path(path, padded, first) == (
        resolve_reformated_path(path, padded, first)
    )


@pytest.mark.parametrize("path", BRACKET_PATHS + PLAIN_PATHS)
def test_get_padding_resolve_variant(path):
    assert paths.get_padding(path) == resolve_padding_from_path(path)


@pytest.mark.parametrize("path", PRINTF_PATHS + PLAIN_PATHS)
@pytest.mark.parametrize("padded", [True, False])
def test_reformat_path_hiero_variant(path, padded):
    assert paths.reformat_path(path, padded) == hiero_reformated_path(
        path, padded)


def test_reformat_path_hiero_variant_wrong_padding():
    """Deliberate difference.

    Hiero takes the last number of the whole path as the padding, so digits
    after the token give a wrong width.
    """
    path = "plate.%04d.v02"
    assert hiero_reformated_path(path) == "plate.%02d.v02"
    assert paths.reformat_path(path) == "plate.%04d.v02"


@pytest.mark.parametrize(
    "path, padding",
    [
        ("plate.####.exr", 4),
        ("plate.%02d.exr", 2),
        ("plate.%04d.exr", 4),
        ("plate.0001.exr", 4),
        ("plate_0001.exr", 4),
        ("plate.######.exr", 6),
        ("plate.exr", None),
    ],
)
def test_pattern_and_padding_hiero_variant(path, padding):
    found, hiero_padding = hiero_sequence_pattern_and_padding(path)
    assert hiero_padding == padding
    assert paths.get_padding(path, allow_frame_numbers=True) == padding
    pattern = paths.parse_sequence_path(path, allow_frame_numbers=True)
    if padding is None:
        assert pattern is None
    else:
        assert pattern.padding == padding


@pytest.mark.parametrize(
    "filename",
    [
        "plate.1001.exr",
        "plate.0001.exr",
        "plate_v01_0100.exr",
        "/shots/sh010/plate.1001.exr",
        "plate.10001.dpx",
        "plate.exr",
        "plate.mov",
    ],
)
@pytest.mark.parametrize("padded", [True, False])
def test_reformat_frame_filename_flame_variant(filename, padded):
    assert paths.reformat_frame_filename(filename, padded) == (
        flame_api_reformatted_filename(filename, padded)
    )


def test_reformat_frame_filename_flame_variant_inner_number():
    """Deliberate difference.

    Flame rewrites the first `.<digits>.` it sees but measures the padding
    on the last one; the shared function uses the one before the extension
    for both.
    """
    name = "shot.010.plate.1001.exr"
    assert flame_api_reformatted_filename(name) == "shot.%04d.plate.1001.exr"
    assert paths.reformat_frame_filename(name) == "shot.010.plate.%04d.exr"


@pytest.mark.parametrize(
    "filename",
    [
        "plate.1001.exr",
        "plate.0001.exr",
        "plate_0001.dpx",
        "/shots/sh010/plate.1001.EXR",
        "plate.1001.mov",
        "plate.exr",
        "plate",
    ],
)
def test_get_frame_flame_variants(filename):
    # api/lib.py variant: any extension
    assert paths.get_frame(filename) == flame_api_frame_from_filename(
        filename)
    # otio/utils.py variant: image extensions only
    assert paths.get_frame(filename, IMAGE_EXTENSIONS) == (
        flame_otio_frame_from_filename(filename)
    )


def test_get_frame_extensions_are_case_insensitive():
    assert paths.get_frame("plate.1001.EXR", {".exr"}) == "1001"
    assert paths.get_frame("plate.1001.mov", {".exr"}) is None


@pytest.mark.parametrize(
    "path, head, tail, notation, padding, first, last",
    [
        ("a/plate.[0001-1008].exr", "a/plate.", ".exr", "bracket", 4,
         "0001", "1008"),
        ("plate.%04d.exr", "plate.", ".exr", "printf", 4, None, None),
        ("plate.%d.exr", "plate.", ".exr", "printf", None, None, None),
        ("plate.####.exr", "plate.", ".exr", "hash", 4, None, None),
        ("plate.1001.exr", "plate.", ".exr", "frame", 4, "1001", "1001"),
    ],
)
def test_parse_sequence_path_notations(
    path, head, tail, notation, padding, first, last
):
    pattern = paths.parse_sequence_path(path, allow_frame_numbers=True)
    assert (
        pattern.head, pattern.tail, pattern.notation, pattern.padding,
        pattern.first_frame, pattern.last_frame,
    ) == (head, tail, notation, padding, first, last)


def test_frame_numbers_are_opt_in():
    assert paths.parse_sequence_path("clip_0010.mov") is None
    assert paths.reformat_path("clip_0010.mov") == "clip_0010.mov"
    assert paths.get_padding("plate.0001.exr") is None


def test_hash_path_to_printf():
    """Traypublisher CSV ingest: `file.###.exr` > `file.%03d.exr`."""
    assert paths.reformat_path("file.###.exr") == "file.%03d.exr"
    assert paths.reformat_path("file.###.exr", padded=False) == "file.%d.exr"


def test_printf_width_is_normalised():
    assert paths.reformat_path("plate.%4d.exr") == "plate.%04d.exr"


def test_sequence_in_last_path_part_wins():
    path = "/shots/[010-020]/plate.[0001-0100].exr"
    assert paths.reformat_path(path) == "/shots/[010-020]/plate.%04d.exr"


def test_malformed_bracket_is_left_alone():
    """Resolve raises IndexError on `[` without a range; we do not."""
    assert paths.reformat_path("plate[final].exr") == "plate[final].exr"
    assert paths.get_padding("plate[final].exr") is None


@pytest.mark.parametrize(
    "path", BRACKET_PATHS + PRINTF_PATHS + ["plate.####.exr"]
)
def test_reformat_is_idempotent(path):
    once = paths.reformat_path(path)
    assert paths.reformat_path(once) == once
