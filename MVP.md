# Editorial MVP (proof of work)

The MVP checks, on two hosts, whether one shared editorial addon makes the
host addons smaller and easier to work on. It replaces the phase plan of
[ROADMAP.md](ROADMAP.md) until the MVP review (Roy, Robin, Jakub) decides
what comes next.

## Scope

Hosts: **Hiero and Flame**. Resolve and Traypublisher are left out.

In:

- OTIO timeline export of both hosts through `otio/builder.py`, with retime
  effects (speed, reverse, freeze frame, time warps) from `otio/effects.py`.
- Shot naming and hierarchy (`shots/hierarchy.py`) and vertical sync
  (`shots/vertical_sync.py`), one implementation for both hosts.
- The clip creator: settings, attribute definitions and the shot, plate and
  audio sub-instance data, shared through mixins. Hosts keep their creator
  classes, identifiers and the metadata I/O (Hiero tags, Flame markers).
- Retime options in both hosts: include handles, retimed handles, retimed
  frame range (Hiero gains them).
- Creator settings owned by `editorial`, as profiles per host.

Out: collectors beyond the retime options, the editorial package, feature
parity beyond retimes, Resolve, Traypublisher, `otio/paths.py` adoption.

## Branches

| Repo | MVP branch | Cut from |
| --- | --- | --- |
| ayon-editorial | `develop-editorial-mvp` | `develop` |
| ayon-hiero | `develop-editorial-mvp` | `develop` |
| ayon-flame | `develop-editorial-mvp` | `develop-minor` (has the OTIO install hook) |

One PR per repo into `develop-editorial-mvp`. The MVP never touches
`develop` or `develop-minor`.

## Layers

Shared logic is plain data in layer 0, so the test suite covers it without
`ayon_core` or a host:

| Module | Layer | Holds |
| --- | --- | --- |
| `shots/clip.py` | 0 | `ClipInfo`, what a host reads from one timeline clip |
| `shots/hierarchy.py` | 0 | `ShotHierarchySolver`: tokens, `#` padding, count, rename, parents, folder path, product name |
| `shots/vertical_sync.py` | 0 | `VerticalSync`: hero track matching, product name de-duplication |
| `shots/options.py` | 0 | the creator attribute schema as data, profile lookup, hidden values |
| `shots/instances.py` | 0 | shot, plate and audio sub-instance data |
| `shots/retime.py` | 0 | include handles, retimed handles, retimed frame range |
| `create/attr_defs.py` | 1 | schema data to `ayon_core` attribute definitions |
| `create/mixins.py` | 1 | creator mixins the host creators inherit |

A host implements only: the selection, reading a clip into `ClipInfo`, the
video track names, the clip rename, and the metadata I/O.

## Settings

`project_settings["editorial"]["create"]["CreateShotClip"]["profiles"]`:
a list of profiles filtered by `host_names` and `task_types` (empty matches
all; the most specific match wins, as `ayon_core.lib.filter_profiles`).
Every profile has the same unified attribute set; `overrides` lists the
attributes the artist may change in the creator, the rest are taken from
the profile and hidden. A host can only show the attributes it supports
(`useShotName` and `segmentIndex` are Flame only).

Defaults: one profile for `hiero` and one for `flame`, with each host's
current defaults.

The hosts lose their `create/CreateShotClip` settings. Stored studio and
project overrides of those are not moved: the server converts only an
addon's own overrides. Moving them is an open point for the MVP review.

## Releases

- Hosts: `ayon_required_addons = {"editorial": ">=0.2.0,<1.0.0"}`.
- `editorial`: lists the hosts in `ayon_compatible_addons` (a warning only),
  so `editorial` is released first and the hosts follow.
- No breaking change of the public API (`shots/`, `create/`, `otio/`) or
  the settings within a major version.

| `editorial` change | Host release |
| --- | --- |
| bug fix, range or retime math | no |
| new or changed shared setting or creator attribute | no |
| new API a host must call, new data from the host | yes, raise the minimum |
| breaking change | `editorial` major and every host |

## What the MVP measures

1. Lines removed from each host and added to `editorial`.
2. What stays in each host and why.
3. Readability: the host creator before and after.
4. An older workfile still publishes (backward compatibility).
5. Admin steps: release `editorial` alone (a fix, a new setting) and update
   the bundle with no host release.

## Testing inside the hosts

`tests/host/` holds scripts to paste into Hiero's Script Editor and Flame's
Python console. They compare the new export with the reference exporter on
the open sequence and run the shot solver on the selection. They print a
short report; nothing is published.
