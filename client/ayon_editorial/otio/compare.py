"""Structural comparison of two OpenTimelineIO files.

Used to prove that an export built through `builder.py` equals the export
of the host code it replaces. Both files are read in the same process and
turned into plain trees, so schema upgrades (`Clip.1` against `Clip.2`)
look the same on both sides.

Dicts are compared by key set (key order is ignored), lists keep their
order. A `RationalTime` with value 0 equals any other zero time, whatever
its rate. Rates and values are never rescaled: a changed rate is a
difference.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import math
import sys
from dataclasses import asdict, dataclass
from typing import Any, List, Optional, Sequence, Tuple

import opentimelineio as otio

__all__ = (
    "CompareOptions",
    "Difference",
    "compare_files",
    "compare_timelines",
    "format_differences",
    "main",
    "normalise",
)

_SCHEMA_KEY = "OTIO_SCHEMA"
_RATIONAL_TIME = "RationalTime."


@dataclass(frozen=True)
class Difference:
    """One difference between two trees.

    Attributes:
        path: Readable location, e.g. `tracks[0:"V1"].children[2:Clip "a"]`.
        kind: `changed`, `missing` (only left), `added` (only right) or
            `type` (different value types).
        left: Value on the left side.
        right: Value on the right side.
    """

    path: str
    kind: str
    left: Any
    right: Any


@dataclass(frozen=True)
class CompareOptions:
    """Tuning of the comparison.

    Attributes:
        tolerance: Absolute tolerance on RationalTime values and floats.
        rate_tolerance: Relative tolerance on rates, so 23.976 against
            23.976024 is a difference.
        ignore: `fnmatch` patterns on the path, e.g.
            `*.metadata.Date Modified`.
        loose_numbers: When True `1 == 1.0`; otherwise int against float
            is a `type` difference.
        max_differences: Stop after this many differences, 0 for all.
    """

    tolerance: float = 1e-6
    rate_tolerance: float = 1e-9
    ignore: Tuple[str, ...] = ()
    loose_numbers: bool = False
    max_differences: int = 0


class _Full(Exception):
    """Raised internally when `max_differences` is reached."""


def normalise(obj: Any) -> Any:
    """Turn an OTIO object into a plain tree of dicts and lists.

    Args:
        obj: Any serializable OTIO object.

    Returns:
        The parsed JSON of `write_to_string(obj)`.
    """
    return json.loads(otio.adapters.write_to_string(obj, "otio_json"))


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _close(left: float, right: float, **kwargs: float) -> bool:
    if math.isnan(left) or math.isnan(right):
        return math.isnan(left) and math.isnan(right)
    return math.isclose(left, right, **kwargs)


def _label(index: int, item: Any) -> str:
    if not isinstance(item, dict) or "name" not in item:
        return str(index)
    kind = str(item.get(_SCHEMA_KEY, "")).split(".")[0]
    name = json.dumps(item["name"], ensure_ascii=False)
    return f"{index}:{kind} {name}" if kind else f"{index}:{name}"


class _Walker:
    def __init__(self, options: CompareOptions) -> None:
        self.options = options
        self.found: List[Difference] = []

    def add(self, path: str, kind: str, left: Any, right: Any) -> None:
        self.found.append(Difference(path, kind, left, right))
        limit = self.options.max_differences
        if limit and len(self.found) >= limit:
            raise _Full

    def ignored(self, path: str) -> bool:
        return any(
            fnmatch.fnmatchcase(path, pattern)
            for pattern in self.options.ignore
        )

    def walk(self, path: str, left: Any, right: Any) -> None:
        if path and self.ignored(path):
            return
        if isinstance(left, dict) and isinstance(right, dict):
            self.walk_dicts(path, left, right)
        elif isinstance(left, list) and isinstance(right, list):
            self.walk_lists(path, left, right)
        elif _is_number(left) and _is_number(right):
            self.walk_numbers(path, left, right)
        elif type(left) is not type(right):
            self.add(path, "type", left, right)
        elif left != right:
            self.add(path, "changed", left, right)

    def walk_dicts(self, path: str, left: dict, right: dict) -> None:
        schema = left.get(_SCHEMA_KEY)
        if (
            isinstance(schema, str)
            and schema.startswith(_RATIONAL_TIME)
            and schema == right.get(_SCHEMA_KEY)
            and {"value", "rate"} <= left.keys() & right.keys()
        ):
            self.walk_rational_times(path, left, right)
            return
        for key in left:
            child = f"{path}.{key}" if path else str(key)
            if self.ignored(child):
                continue
            if key not in right:
                self.add(child, "missing", left[key], None)
            else:
                self.walk(child, left[key], right[key])
        for key in right:
            if key not in left:
                child = f"{path}.{key}" if path else str(key)
                if not self.ignored(child):
                    self.add(child, "added", None, right[key])

    def walk_rational_times(self, path: str, left: dict, right: dict) -> None:
        """Compare two RationalTime dicts; zero equals zero at any rate."""
        values = (left["value"], right["value"])
        if all(_is_number(v) for v in values) and all(v == 0 for v in values):
            return
        for key, kwargs in (
            ("rate", {"rel_tol": self.options.rate_tolerance}),
            ("value", {"abs_tol": self.options.tolerance}),
        ):
            a, b = left[key], right[key]
            child = f"{path}.{key}"
            if self.ignored(child):
                continue
            if not (_is_number(a) and _is_number(b)):
                self.walk(child, a, b)
            elif not _close(float(a), float(b), **kwargs):
                self.add(child, "changed", a, b)

    def walk_lists(self, path: str, left: list, right: list) -> None:
        for index in range(max(len(left), len(right))):
            if index < len(left) and index < len(right):
                child = f"{path}[{_label(index, left[index])}]"
                self.walk(child, left[index], right[index])
            elif index < len(left):
                child = f"{path}[{_label(index, left[index])}]"
                if not self.ignored(child):
                    self.add(child, "missing", left[index], None)
            else:
                child = f"{path}[{_label(index, right[index])}]"
                if not self.ignored(child):
                    self.add(child, "added", None, right[index])

    def walk_numbers(self, path: str, left: Any, right: Any) -> None:
        if (
            isinstance(left, float) != isinstance(right, float)
            and not self.options.loose_numbers
        ):
            self.add(path, "type", left, right)
        elif not _close(
            float(left), float(right), abs_tol=self.options.tolerance
        ):
            self.add(path, "changed", left, right)


def compare_timelines(
    left: Any, right: Any, options: Optional[CompareOptions] = None
) -> List[Difference]:
    """Compare two OTIO objects.

    Args:
        left: Timeline (or any OTIO object).
        right: Object to compare against.
        options: Comparison options, defaults when omitted.

    Returns:
        The differences in document order; empty when equal.
    """
    walker = _Walker(options or CompareOptions())
    try:
        walker.walk("", normalise(left), normalise(right))
    except _Full:
        pass
    return walker.found


def compare_files(
    left: str, right: str, options: Optional[CompareOptions] = None
) -> List[Difference]:
    """Read two OTIO files and compare them.

    Args:
        left: Path of the first file.
        right: Path of the second file.
        options: Comparison options, defaults when omitted.

    Returns:
        The differences; empty when equal.
    """
    return compare_timelines(
        otio.adapters.read_from_file(left),
        otio.adapters.read_from_file(right),
        options,
    )


def _short(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return text if len(text) <= 120 else text[:117] + "..."


def format_differences(diffs: Sequence[Difference]) -> str:
    """Render differences as `PATH: KIND LEFT != RIGHT` lines.

    Args:
        diffs: Differences from `compare_files`.

    Returns:
        One line per difference, then a count line.
    """
    lines = [
        f"{d.path or '<root>'}: {d.kind} {_short(d.left)} != {_short(d.right)}"
        for d in diffs
    ]
    count = len(diffs)
    lines.append(f"{count} difference{'' if count == 1 else 's'}")
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="otio_compare", description="Compare two OTIO files."
    )
    parser.add_argument("left")
    parser.add_argument("right")
    parser.add_argument("--tolerance", type=float, default=1e-6)
    parser.add_argument("--rate-tolerance", type=float, default=1e-9)
    parser.add_argument("--ignore", action="append", default=[])
    parser.add_argument("--loose-numbers", action="store_true")
    parser.add_argument("--max", type=int, default=0, dest="max_differences")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the command line tool.

    Args:
        argv: Arguments without the program name, `sys.argv` if None.

    Returns:
        0 when equal, 1 when different, 2 on usage error or unreadable
        file.
    """
    try:
        args = _parser().parse_args(argv)
    except SystemExit as error:
        return error.code if isinstance(error.code, int) else 2
    options = CompareOptions(
        tolerance=args.tolerance,
        rate_tolerance=args.rate_tolerance,
        ignore=tuple(args.ignore),
        loose_numbers=args.loose_numbers,
        max_differences=args.max_differences,
    )
    try:
        diffs = compare_files(args.left, args.right, options)
    except Exception as error:  # unreadable or invalid file
        print(f"otio_compare: {error}", file=sys.stderr)
        return 2
    if args.as_json:
        print(json.dumps([asdict(d) for d in diffs], indent=2))
    elif diffs:
        print(format_differences(diffs))
    return 1 if diffs else 0
