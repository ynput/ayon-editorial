# Roadmap

The roadmap is generated from `.github/roadmap.yml`. Edit that manifest,
never the issue bodies. Sync with:

```
uv run --with pyyaml tools/roadmap_sync.py [--dry-run]
```

- Roadmap issue: <https://github.com/ynput/ayon-editorial/issues/1>
- Project: <https://github.com/orgs/ynput/projects/77>

## Vision

Move the editorial code that Flame, Hiero, Resolve and Traypublisher each
carry a copy of into one DCC-agnostic addon, `ayon-editorial`. Host addons
keep only what talks to their host API. Every addon that uses the shared
code declares `editorial` in `ayon_required_addons`.

## Scope

In scope:

- OTIO helpers: timecode and frames, sequence-path padding, the `AYONData`
  marker codec, retime effects.
- Building the OTIO timeline from host clips.
- Shot naming, hierarchy and vertical sync.
- The clip creator framework, shared shot, plate and audio collector logic
  and the editorial package.
- One OpenTimelineIO install hook for hosts with their own Python (Flame,
  Resolve).
- Creator feature parity between hosts once the code is shared.

Out of scope:

- Host API calls. They stay in the host addons.
- Settings. They stay in each host addon; the `editorial` category is
  empty for now.
- ayon-core's OTIO publish plugins. They stay in core until P7.2.
- A clip name tokenizer UI (the shared tokens make one possible later).

Ideas to consider, not planned: farm rendering of editorial extraction
(P7.4), review tools using the shared builder (P7.5), timeline publishing
from Unreal (P7.3).

## Duplication map

Where each area is implemented today, by host.

| Area | Flame | Hiero | Resolve | Traypublisher |
| --- | --- | --- | --- | --- |
| OTIO helpers | `otio/utils.py` | `api/otio/utils.py` | `otio/utils.py` | uses ayon-core |
| Timeline export | `otio/flame_export.py` | `api/otio/hiero_export.py` | `otio/davinci_export.py` | reads EDL or OTIO files |
| Shot naming and hierarchy | `PublishClip` | `PublishClip` (most complete) | `PublishClip` | `ShotMetadataSolver` in `api/editorial.py` |
| Clip creator | `create_shot_clip.py` | `create_shot_clip.py` | `create_shot_clip.py` | Simple and Advanced Editorial creators |
| Collectors | `collect_shots.py`, `collect_plate_from_timeline.py`, `collect_audio.py` | `collect_shots.py`, `collect_plates.py`, `collect_audio.py` | same names | `collect_shot_instances.py` and editorial collectors |
| Editorial package | none | `extract_editorial_package.py` | `extract_editorial_package.py` | `extract_editorial_pckg.py` |
| OTIO install | `pre_opentimelineio_install.py` | ships OTIO | none (TODO in `pre_resolve_setup.py`) | uses ayon-core |
| Retime | in export, `tw_bake.py` (timewarp XML) | in export | in export | none |

## Target architecture

```
host addon (host API calls only)
   | plain data, files, OTIO objects
   v
ayon_editorial layer 1: create/, publish/, lib/   -> ayon_core
   |
   v
ayon_editorial layer 0: otio/, shots/, editorial_package.py
```

- Layer 0 (`otio/`, `shots/`, `editorial_package.py`): standard library,
  `opentimelineio`, `clique`. Works on files and OTIO objects.
- Layer 1 (`create/`, `publish/`, `lib/`): also `ayon_core` and
  `ayon_applications`.
- No host API, Qt at import time, or `ayon_<host>` import anywhere.
- Hosts keep their creator classes and plugin identifiers and add the
  shared mixins. Frozen contracts are in [AGENTS.md](AGENTS.md).
- The module map is in
  [client/ayon_editorial/AGENTS.md](client/ayon_editorial/AGENTS.md).

## Phases

| Phase | Epic | Goal | Release |
| --- | --- | --- | --- |
| P0 Bootstrap | [#2](https://github.com/ynput/ayon-editorial/issues/2) | Packaged, tested, empty addon with agent instructions | 0.0.1 |
| P1 OTIO in DCCs | [#8](https://github.com/ynput/ayon-editorial/issues/8) | One OTIO install hook for every host | 0.1.0 |
| P2 OTIO library | [#12](https://github.com/ynput/ayon-editorial/issues/12) | Shared OTIO helpers and timeline builder | 0.2.0 |
| P3 Shots and creators | [#23](https://github.com/ynput/ayon-editorial/issues/23) | Shared shot naming and clip creator framework | 0.3.0 |
| P4 Publish helpers | [#32](https://github.com/ynput/ayon-editorial/issues/32) | Shared shot, plate and audio collector logic | 0.4.0 |
| P5 Editorial package | [#38](https://github.com/ynput/ayon-editorial/issues/38) | Shared editorial package logic | 0.5.0 |
| P6 Creator parity | [#43](https://github.com/ynput/ayon-editorial/issues/43) | Features only one host has, in every host | 0.6.0 |
| P7 Release and future | [#51](https://github.com/ynput/ayon-editorial/issues/51) | First stable release, later moves and ideas | 1.0.0 |

Each library phase is released before the host PRs that adopt it are
merged. Host PRs add `"editorial": ">=0.N.0"` to `ayon_required_addons`
and get the `bump minor` label.

Host PRs target the host's `develop-minor` branch (created from its
`develop`), not `develop`, so roadmap work stays apart from regular
development. See "Branching in host repos" in [AGENTS.md](AGENTS.md).

## Editorial versions and host minimums

Host application minimums are the support floor: Hiero 14, Flame 2024,
Resolve 18 (P2.1 confirms them). The host addon version that adopts each
editorial release is set when that host PR is released.

| Editorial | Needs from the host | Host steps that require it |
| --- | --- | --- |
| 0.0.1 | nothing (empty addon) | none |
| 0.1.0 | Python of the host able to `pip install` OTIO | P1.2 Flame, P1.3 Resolve |
| 0.2.0 | OTIO 0.15 or newer | P2.7 to P2.10 |
| 0.3.0 | same | P3.5 to P3.8 |
| 0.4.0 | same | P4.2 to P4.5 |
| 0.5.0 | same | P5.2 to P5.4 |
| 0.6.0 | same | P6 steps |
| 1.0.0 | same | none |

## OTIO support matrix

Recorded by P2.1 from the addon code and docs. A cell marked "human" can
only be read inside the host application: an agent cannot run one. To fill
it, run this in the host's Python console (Hiero script editor, Flame
`python` shell, Resolve console with Python 3) and write the result here:

```
import sys, opentimelineio as o; print(sys.version.split()[0], o.__version__)
```

| Host | Version | Python | OTIO source | OTIO version |
| --- | --- | --- | --- | --- |
| Hiero / Nuke Studio | 14 | human | bundled | human |
| Hiero / Nuke Studio | 15, 16 | human | bundled | human |
| Flame | 2024 | human | pre-launch hook (P1) | installed by the hook, `>=0.15,<0.18` |
| Flame | 2025, 2026 | human | pre-launch hook (P1) | installed by the hook, `>=0.15,<0.18` |
| DaVinci Resolve | 18 | up to 3.9.13 (`ayon_resolve/README.markdown`) | pre-launch hook (P1) | installed by the hook, `>=0.15,<0.18` |
| DaVinci Resolve | 19, 20 | up to 3.9.13 (same README, tested on 21) | pre-launch hook (P1) | installed by the hook, `>=0.15,<0.18` |
| Traypublisher | any | AYON launcher | ayon-core | 0.16.0 (ayon-core client dependency) |

Supported floor: **OTIO 0.15**, from the oldest hosts. `otio/compat.py`
(`MIN_OTIO_VERSION`) holds it; `check_otio_version()` enforces it. The
Traypublisher editorial package validator already asks for 0.16.0 or newer
to read newer OTIO schemas.

OTIO API differences handled in `otio/compat.py`:

| Change | OTIO | Shim |
| --- | --- | --- |
| `each_clip`, `each_child` renamed `find_clips`, `find_children` | 0.16 | `find_clips`, `each_clip`, `find_children` |
| Old names removed | 0.17 | same |
| `find_children` takes `descended_from_type` before `search_range` | 0.16 | the shims pass keywords only |

CI covers OTIO 0.15, 0.16 and 0.17 on Python 3.9, and the latest OTIO on
Python 3.11.

## Earlier discussions this roadmap resolves

Each asked for the same editorial behaviour in every host. The step that
handles it links back to it.

- ynput/ayon-hiero#65, ynput/ayon-resolve#56: clip name tokenizer in every
  editorial creator (only Traypublisher has it)
- ynput/ayon-hiero#15, ynput/ayon-resolve#39: deeper shot folder hierarchy
- ynput/ayon-flame#68, ynput/ayon-hiero#83, ynput/ayon-resolve#70,
  ynput/ayon-traypublisher#100: instance parenting in all editorial
  integrations (root: ynput/ayon-core#874)
- ynput/ayon-flame#176, ynput/ayon-flame#178: handle clamping consistent
  across hosts (after ynput/ayon-resolve#132)
- ynput/ayon-resolve#40: workfile version-up consistent across hosts
- ynput/ayon-flame#109, ynput/ayon-flame#28, ynput/ayon-hiero#29: retime
  consolidation across Flame and Hiero
- ynput/ayon-hiero#69, ynput/ayon-hiero#162: vertical sync behaviour
- ynput/ayon-resolve#2, ynput/ayon-resolve#82, ynput/ayon-traypublisher#7,
  ynput/ayon-core#1400: OpenTimelineIO version differences between hosts
