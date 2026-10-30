"""OpenTimelineIO version differences in one place.

Replaces the `try: find_clips() except AttributeError: each_clip()` blocks
copied in `ayon_hiero/api/otio/utils.py`, `ayon_resolve/otio/utils.py` and
`ayon_resolve/api/lib.py`, and the unguarded `import opentimelineio` of
every host. Nothing is imported at module level except the standard
library, so a host can import this module on a machine without OTIO and
get a clear error from `require_otio` instead of a bare `ImportError`.

OTIO 0.16 renamed `each_clip` and `each_child` to `find_clips` and
`find_children`; 0.17 and newer no longer have the old names.
"""
from __future__ import annotations

import importlib
import re
from typing import Any, List, Optional, Tuple

__all__ = (
    "MIN_OTIO_VERSION",
    "OTIOVersionError",
    "check_otio_version",
    "each_clip",
    "find_children",
    "find_clips",
    "get_otio_version",
    "is_otio_supported",
    "parse_version",
    "require_otio",
)

MIN_OTIO_VERSION: Tuple[int, ...] = (0, 15)

_VERSION_RE = re.compile(r"\s*(\d+(?:\.\d+)*)")


class OTIOVersionError(ImportError):
    """OpenTimelineIO is missing or older than the supported floor."""


def parse_version(text: Optional[str]) -> Tuple[int, ...]:
    """Parse the leading numeric part of a version string.

    Args:
        text: Version such as `0.17.0` or `0.16.0.dev1`.

    Returns:
        tuple[int, ...]: Numbers of the version, empty when unparsable.
    """
    match = _VERSION_RE.match(text or "")
    if not match:
        return ()
    return tuple(int(part) for part in match.group(1).split("."))


def require_otio() -> Any:
    """Import `opentimelineio`, or fail with a message a user can act on.

    Returns:
        module: The `opentimelineio` module.

    Raises:
        OTIOVersionError: When it cannot be imported.
    """
    try:
        return importlib.import_module("opentimelineio")
    except ImportError as exc:
        raise OTIOVersionError(
            "OpenTimelineIO is not installed in this Python environment "
            f"(supported: {_format(MIN_OTIO_VERSION)} or newer): {exc}"
        ) from exc


def get_otio_version() -> Tuple[int, ...]:
    """Get the version of the importable OpenTimelineIO.

    Raises:
        OTIOVersionError: When OTIO cannot be imported.
    """
    return parse_version(getattr(require_otio(), "__version__", ""))


def check_otio_version(
    minimum: Tuple[int, ...] = MIN_OTIO_VERSION,
) -> Tuple[int, ...]:
    """Fail when the importable OpenTimelineIO is older than `minimum`.

    Args:
        minimum: Oldest accepted version.

    Returns:
        tuple[int, ...]: The version found.

    Raises:
        OTIOVersionError: When OTIO is missing, its version cannot be read
            or it is older than `minimum`.
    """
    version = get_otio_version()
    if not version or version < tuple(minimum):
        found = _format(version) if version else "an unreadable version"
        raise OTIOVersionError(
            f"OpenTimelineIO {_format(minimum)} or newer is required, "
            f"found {found}."
        )
    return version


def is_otio_supported(minimum: Tuple[int, ...] = MIN_OTIO_VERSION) -> bool:
    """Tell whether a usable OpenTimelineIO is importable."""
    try:
        check_otio_version(minimum)
    except OTIOVersionError:
        return False
    return True


def find_children(
    item: Any,
    search_range: Any = None,
    shallow_search: bool = False,
    descended_from_type: Any = None,
) -> List[Any]:
    """List the children of a composition on any OTIO version.

    Uses `find_children` (0.16+), else `each_child` (0.15).

    Args:
        item: A `Timeline` or composition (`Track`, `Stack`).
        search_range: Only children overlapping this `TimeRange`.
        shallow_search: Do not descend into nested compositions.
        descended_from_type: Only children of this type.
    """
    method = getattr(item, "find_children", None)
    if method is None:
        method = item.each_child
    # Keywords only: the two methods order their parameters differently.
    kwargs = {"search_range": search_range, "shallow_search": shallow_search}
    if descended_from_type is not None:
        kwargs["descended_from_type"] = descended_from_type
    return list(method(**kwargs))


def find_clips(
    item: Any,
    search_range: Any = None,
    shallow_search: bool = False,
) -> List[Any]:
    """List the clips of a timeline or composition on any OTIO version.

    Uses `find_clips` (0.16+), else `each_clip` (0.15).

    Args:
        item: A `Timeline` or composition (`Track`, `Stack`).
        search_range: Only clips overlapping this `TimeRange`.
        shallow_search: Do not descend into nested compositions.
    """
    method = getattr(item, "find_clips", None)
    if method is None:
        method = item.each_clip
    return list(
        method(search_range=search_range, shallow_search=shallow_search)
    )


def each_clip(item: Any, search_range: Any = None):
    """Iterate the clips of a timeline or composition on any OTIO version.

    Same as `find_clips`, for call sites written as a loop.
    """
    return iter(find_clips(item, search_range))


def _format(version: Tuple[int, ...]) -> str:
    return ".".join(str(part) for part in version)
