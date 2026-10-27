# AYON Editorial

DCC-agnostic editorial (OpenTimelineIO) library for AYON host addons.

Flame, Hiero, Resolve and Traypublisher each carry a copy of the same
editorial code: OTIO helpers, timeline export, shot naming and hierarchy,
the clip creator workflow and the editorial package. This addon holds one
DCC-agnostic copy of that code. Host addons keep only what talks to their
host API, and declare `editorial` in `ayon_required_addons` of their
`package.py`.

The addon is not a host: it has no application, launcher action or
plugins of its own. Its settings category, `editorial`, is empty for now;
editorial settings stay in each host addon.

The work is planned in the
[roadmap issue](https://github.com/ynput/ayon-editorial/issues/1) and the
[Editorial Unification project](https://github.com/orgs/ynput/projects/77).

See [ROADMAP.md](ROADMAP.md), [AGENTS.md](AGENTS.md) and
[AI-CONTRIBUTION.md](AI-CONTRIBUTION.md) for the plan and how to contribute.

## Layout

```
client/ayon_editorial/   client code, imported as `ayon_editorial`
server/                  server addon and settings
create_package.py        builds the addon package
```

## Build the package

```bash
python create_package.py            # package/editorial-<version>.zip
python create_package.py --skip-zip # unzipped, into package/editorial/<version>/
```

Upload the zip on the AYON server (Studio settings → Bundles → Addons) and
add it to a bundle with the host addons that use it.
