# AGENTS.md — ayon-editorial

## Overview

DCC-agnostic editorial (OpenTimelineIO) library addon for AYON. Flame,
Hiero, Resolve and Traypublisher each carry a copy of the same editorial
code; this addon holds one copy. Host addons keep only what talks to their
host API and declare `editorial` in `ayon_required_addons`.

It is not a host: no application, no launcher action, no plugins of its
own. The `editorial` settings category is empty; settings stay in each
host addon.

Work is planned in [ROADMAP.md](ROADMAP.md). Read
[AI-CONTRIBUTION.md](AI-CONTRIBUTION.md) before starting a step.

## Layout

```
client/ayon_editorial/   client code, imported as `ayon_editorial`
server/                  server addon and settings (`settings/conversion.py`)
tests/                   pytest suite, never imports `ayon_core`
tools/                   manage scripts, roadmap sync (not packaged)
package.py               addon metadata
create_package.py        builds the package
```

The module map is in
[client/ayon_editorial/AGENTS.md](client/ayon_editorial/AGENTS.md).

## Layer rules

| Layer | Modules | May import |
| --- | --- | --- |
| 0 | `otio/`, `shots/`, `editorial_package.py` | standard library, `opentimelineio`, `clique`, layer 0 |
| 1 | `create/`, `publish/`, `lib/` | layer 0 and `ayon_core`, `ayon_applications` |

- Layer 0 works on files and OTIO objects, never host objects.
- Nowhere: a host API (`hiero`, `flame`, `DaVinciResolveScript`,
  `unreal`, `nuke`), Qt at import time, or an `ayon_<host>` addon.
- `addon.py` has light imports and is safe at launch time.
- `tests/test_dcc_agnostic.py` enforces these rules.

## Commands

```
./tools/manage.sh create-env   # create or update the venv
./tools/manage.sh run-tests    # pytest
./tools/manage.sh ruff-check   # ruff
./tools/manage.sh ruff-fix     # ruff --fix
./tools/manage.sh codespell    # spelling
./tools/manage.sh run <cmd>    # any command in the venv
python create_package.py --skip-zip   # build the package layout
```

CI: Python 3.9 with OTIO 0.15, 0.16 and 0.17, plus Python 3.11 with the
latest OTIO. Ruff follows ayon-core's config (E/F/W, py39, line length 79).

## OTIO and Python limits

- Support floor: Hiero 14, Flame 2024, Resolve 18. So Python 3.9 and
  OTIO 0.15 or newer. P2.1 confirms the floor per host.
- Hiero ships OTIO. Flame and Resolve get it from a pre-launch hook (P1).
  Traypublisher uses ayon-core's OTIO.
- No syntax or stdlib newer than Python 3.9 in shared code. Use
  `from __future__ import annotations`.
- Version differences go through `otio/compat.py` (P2.1), never inline.

## Frozen contracts

Do not change these silently. A change needs its own issue, a conversion
or deprecation path, and a note in the PR.

| Contract | Frozen part |
| --- | --- |
| Creators | `identifier` of every editorial creator |
| Product base types | `editorial`, `shot`, `plate`, `audio`, `editorial_pkg` |
| Plugins | `order`, `families`, `hosts` of every moved or adopted plugin |
| `instance.data` read by ayon-core | `otioClip`, `context.otioTimeline`, `handleStart`, `handleEnd`, `frameStart`, `workfileFrameStart`, `shotDurationFromSource`, `otioReviewClips` |
| Family tags | `otio.clip.ranges`, `otio.resources`, `otio.review.track`, `otio.timeline.workfile`, `otio.trim.video` |
| Timeline marker | name `AYONData` and its `json_metadata` |
| Host settings | the `<host>_sub_products` keys and every host settings path |

Renaming a settings key needs a conversion function in
`server/settings/conversion.py`.

## Branching in host repos

All host-side work of this roadmap (every "Host adoption" step and every
host PR that requires `editorial`) targets the branch `develop-minor` of
the host repository, never `develop`. `develop-minor` is created from the
host's current `develop`, so roadmap work does not mix with regular
development, which keeps releasing patches from `develop`.

- Open host PRs against `develop-minor` and keep it up to date by merging
  `develop` into it.
- `develop-minor` is merged into `develop` only when the host minor
  release that requires `editorial` is made; that is a human decision.
- Create `develop-minor` from `develop` in a host repository when its
  first adoption step starts (done for ayon-flame and ayon-resolve).
- This repository (`ayon-editorial`) has no `develop-minor`: its `develop`
  only carries roadmap work.

## Rules for agents

- Never target `develop` of a host repository with roadmap work, see
  Branching in host repos.
- Never merge, release, or change repository visibility.
- Never claim to have run a host application; write manual steps for a
  human instead.
- Never name or quote a private repository. Check visibility with
  `gh repo view ynput/<name> --json visibility` first.
- Never touch vendor code.
- Python: PEP 8, Google docstrings, `logging` not `print`, type hints,
  dataclasses over dicts.

## Links

- [ROADMAP.md](ROADMAP.md): scope, phases, support matrix
- [AI-CONTRIBUTION.md](AI-CONTRIBUTION.md): workflow, recipes, tiers
- [client/ayon_editorial/AGENTS.md](client/ayon_editorial/AGENTS.md)
- [tests/AGENTS.md](tests/AGENTS.md)
- [Roadmap issue](https://github.com/ynput/ayon-editorial/issues/1) and
  [Project](https://github.com/orgs/ynput/projects/77)
