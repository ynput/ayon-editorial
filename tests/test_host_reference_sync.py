"""Keep the host reference exporters honest.

`tests/resources/host_exports/<host>_reference.py` copies the export code
of a host addon. The copy is only worth something while the host file is
the one that was copied. Each reference header records the git blob of the
host file; this test checks the header, and, when `AYON_EDITORIAL_HOST_ROOT`
points at the folder holding the host checkouts (`ayon-flame`,
`ayon-hiero`, `ayon-resolve`), that the host file still has that blob.

When it fails: read the host change, update the reference and the golden
`.otio` next to it, then update the blob here and in the header.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

RESOURCES = Path(__file__).parent / "resources" / "host_exports"

# host repo, file in it, git blob recorded in the reference header
SOURCES = {
    "flame": [
        ("ayon-flame", "client/ayon_flame/otio/flame_export.py",
         "1e27519d878ecfbd3b4b7f3bce6743742a8616ed"),
        ("ayon-flame", "client/ayon_flame/otio/utils.py",
         "a94c1687b67b88d7f2c526147f7b9dc607880c3d"),
    ],
    "hiero": [
        ("ayon-hiero", "client/ayon_hiero/api/otio/hiero_export.py",
         "7b006f3c5b103314f1f1c0ff05bc3b9a0add9135"),
        ("ayon-hiero", "client/ayon_hiero/api/otio/utils.py",
         "f1b3cffa38f4e34e88f0cb0b3b55d9f8897ba71e"),
    ],
    "resolve": [
        ("ayon-resolve", "client/ayon_resolve/otio/davinci_export.py",
         "6db566dc154d6a84b1c46ad10edbbd253475df67"),
        ("ayon-resolve", "client/ayon_resolve/otio/utils.py",
         "450ec941a55676ee8217b890bff32d1d9867eecf"),
    ],
}
HEADER_BLOBS = {
    # utils of Flame and Resolve are described as "same commit" in the
    # header, without a blob of their own
    "flame": ["1e27519d878ecfbd3b4b7f3bce6743742a8616ed"],
    "hiero": [
        "7b006f3c5b103314f1f1c0ff05bc3b9a0add9135",
        "f1b3cffa38f4e34e88f0cb0b3b55d9f8897ba71e",
    ],
    "resolve": ["6db566dc154d6a84b1c46ad10edbbd253475df67"],
}


@pytest.mark.parametrize("host", sorted(SOURCES))
def test_reference_header_records_the_blobs(host):
    header = (RESOURCES / f"{host}_reference.py").read_text()[:3000]
    for blob in HEADER_BLOBS[host]:
        assert blob in header


@pytest.mark.hostsync
@pytest.mark.skipif(
    not os.environ.get("AYON_EDITORIAL_HOST_ROOT"),
    reason="AYON_EDITORIAL_HOST_ROOT is not set",
)
@pytest.mark.parametrize(
    "host, repo, path, blob",
    [
        (host, repo, path, blob)
        for host, sources in sorted(SOURCES.items())
        for repo, path, blob in sources
    ],
)
def test_host_file_is_the_copied_one(host, repo, path, blob):
    root = Path(os.environ["AYON_EDITORIAL_HOST_ROOT"])
    checkout = root / repo
    if not (checkout / path).is_file():
        pytest.skip(f"{checkout / path} not found")
    actual = subprocess.run(
        ["git", "-C", str(checkout), "hash-object", path],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert actual == blob, (
        f"{repo}/{path} changed since the {host} reference was copied"
    )
