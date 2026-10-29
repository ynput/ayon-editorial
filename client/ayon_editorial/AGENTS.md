# AGENTS.md — client/ayon_editorial

Client package of the addon. Read the root [AGENTS.md](../../AGENTS.md)
first.

## Import rules

| Layer | Modules | May import |
| --- | --- | --- |
| 0 | `otio/`, `shots/`, `editorial_package.py` | standard library, `opentimelineio`, `clique`, layer 0 |
| 1 | `create/`, `publish/`, `lib/` | layer 0, `ayon_core`, `ayon_applications` |

- Layer 0 takes files and OTIO objects. Host objects never cross into it.
- Nowhere: `hiero`, `flame`, `DaVinciResolveScript`, `unreal`, `nuke`, Qt
  at import time, or any `ayon_<host>` package.
- A host that needs host calls implements an adapter (P3.4) and passes
  plain data in.
- `addon.py` is imported at launch: only light imports, no
  `opentimelineio`, no Qt.
- Use relative imports inside the package.
- `tests/test_dcc_agnostic.py` checks all of this with an AST walk.

## Module map

Existing:

| Module | Status |
| --- | --- |
| `__init__.py`, `addon.py`, `version.py` | exists (P0.3) |
| `lib/otio_install.py` | done (P1.1) |
| `otio/compat.py` | done (P2.1) |
| `otio/time.py` | done (P2.2) |
| `otio/paths.py` | done (P2.3) |

`lib/otio_install.py` holds `OTIOInstallHookMixin`, a plain mixin and not a
`PreLaunchHook` subclass: `ayon_applications` runs every `PreLaunchHook`
subclass in a hook module, imported ones too, so a shared base with empty
`app_groups` would run on every launch. A host hook is
`class X(OTIOInstallHookMixin, PreLaunchHook)` and imports only the mixin.

Planned, with the step that adds each:

| Module | Layer | Step | Status |
| --- | --- | --- | --- |
| `otio/markers.py` | 0 | P2.4 | planned |
| `otio/effects.py` | 0 | P2.5 | planned |
| `otio/builder.py` | 0 | P2.6 | planned |
| `shots/hierarchy.py` | 0 | P3.1 | planned |
| `shots/vertical_sync.py` | 0 | P3.2 | planned |
| `create/attr_defs.py` | 1 | P3.3 | planned |
| `create/adapter.py` | 1 | P3.4 | planned |
| `create/mixins.py` | 1 | P3.4 | planned |
| `publish/lib.py` | 1 | P4.1 | planned |
| `editorial_package.py` | 0 | P5.1 | planned |

Outside the package: `tools/otio_compare.py` (P2.6, planned).

## Conventions

- Each module has a module docstring that says what it replaces in the
  hosts.
- Public names are the contract with host addons. Keep them stable and
  list them in `__all__`.
- Dataclasses over dicts (`ClipSpec`, `MediaSpec`).
- Port from the host copies with characterization tests first; see
  [tests/AGENTS.md](../../tests/AGENTS.md).
