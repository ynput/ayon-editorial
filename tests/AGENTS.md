# AGENTS.md — tests

Read the root [AGENTS.md](../AGENTS.md) first.

## Rules

- Tests never import `ayon_core`, a host API or Qt. They run on a plain
  interpreter with `opentimelineio` and `clique`.
- `conftest.py` stubs the `ayon_editorial` package (its real `__init__`
  imports `ayon_core`), so `from ayon_editorial.otio import compat` works.
- Run all: `./tools/manage.sh run-tests`. Run one:
  `./tools/manage.sh run pytest tests/<file>.py -v`.
- Tests must pass on Python 3.9 with OTIO 0.15, 0.16 and 0.17, and on
  Python 3.11 with the latest OTIO.

## Existing tests

| File | Checks |
| --- | --- |
| `test_package.py` | `package.py` metadata fields |
| `test_create_package.py` | `create_package.py --skip-zip` into a temporary folder: `version.py` and the layout |
| `test_dcc_agnostic.py` | layer and import rules (AST walk) |
| `test_roadmap_manifest.py` | `.github/roadmap.yml`: unique IDs, known field values, dependencies without cycles, every issue body renders |
| `test_otio_compat.py` | `otio/compat.py` version helpers and clip search shims |
| `test_otio_time.py` | `otio/time.py`, each host variant of the time helpers |
| `test_otio_paths.py` | `otio/paths.py`, each host variant of the sequence path helpers |
| `test_otio_markers.py` | `otio/markers.py`, the marker lookup of each host and the codec |
| `test_otio_effects.py` | `otio/effects.py`, the ayon-core retime fixtures in `resources/ayon_core_retime/` and the host writers |
| `test_otio_builder.py` | `otio/builder.py`: conform formulas, gap modes, references, markers, effects |
| `test_otio_compare.py` | `otio/compare.py` and the `tools/otio_compare.py` exit codes |
| `test_otio_builder_{flame,hiero,resolve}.py` | the builder against each host reference exporter (`otio_compare`), mutation-sensitive; the specs in `resources/host_exports/<host>_specs.py` are the templates the host adoption PRs copy |
| `test_host_reference_{flame,hiero,resolve}.py` | each reference exporter against its golden `.otio`, on every supported OTIO |
| `test_host_reference_sync.py` | the git blobs recorded in the reference headers; with `AYON_EDITORIAL_HOST_ROOT` set (marker `hostsync`) also that the host files still have them |
| `conftest.py` | shared fixtures; stubs the `ayon_editorial` package so layer 0 modules import without `ayon_core` |

## Fixtures and markers

- Keep fixture files (OTIO exports, EDL, marker JSON) in
  `tests/resources/`. Small files only.
- `tests/resources/host_exports/` holds, per host, the input dict
  (`<host>_input.json`), the reference exporter (`<host>_reference.py`, host
  code copied verbatim, only host reads replaced and marked `HOST-READ`),
  the builder specs (`<host>_specs.py`) and the golden `<host>.otio` written
  by the reference on OTIO 0.15. When a host file changes, update the
  reference, regenerate the golden and the blob in the header and in
  `test_host_reference_sync.py`. The references model the host through fake
  classes: they are not exports from a real host, which stay a manual step
  of each adoption PR.
- Fixtures taken from a host export must come from a public or synthetic
  project, never from client material.
- Markers (registered in `pyproject.toml`): `otio` for tests that need
  OpenTimelineIO installed, `slow` for tests that take noticeably long, `hostsync` for tests that
  need the host addon checkouts (`AYON_EDITORIAL_HOST_ROOT`; skipped
  otherwise, and not run in CI).
  Register a new marker there before using it.

## Characterization tests

Before porting a function out of a host addon, record what each host copy
does today.

1. Collect inputs: the cases the host code handles, including odd ones.
2. Write one test per host variant. Assert the host's current output,
   even where the variants disagree.
3. Port the code. The tests must still pass; a deliberate difference is a
   behaviour change and needs its own note in the PR.
4. Keep the tests after the port: they guard the frozen contracts.

Name them `test_<function>_<host>_<case>`.
