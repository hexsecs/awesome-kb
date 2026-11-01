# Maintainer schema — Awesome KB registry

This repository is the registry for the Awesome KB network. It is itself an
OpenShelf KB (`profile: awesome`) whose listed entities are knowledge bases.

The format is **not** defined here. OpenShelf is defined in
[hexsecs/openkb](https://github.com/hexsecs/openkb); this file contains only
the registry's local rules. Read `kb.yaml` for the declared layout.

## Source of truth

- A knowledge base is **registered** only when it appears in all three
  places, consistently:
  1. `.openshelf/kbs.yaml` — the machine-readable connection list;
  2. `wiki/<page>.md` — its registry page;
  3. `index.md` and `README.md` — the human-readable catalogues.
- A repository that lacks a conforming `kb.yaml` is **planned**, not
  registered. Planned repositories may be named in `README.md`, but must not
  be added to `.openshelf/kbs.yaml`, `index.md`, or `wiki/`.

## Registration criteria

A candidate KB must:

- publish an OpenShelf `kb.yaml` at its repository root;
- use a unique OpenShelf ID;
- provide the L0 title and description in that manifest;
- pass `openshelf lint` with no errors at the commit being registered; and
- be readable at the registered source so agents can fetch it.

Conformance means the KB can be connected and read reliably. It does not
certify the truth, completeness, or quality of its contents.

## Operations

### register

1. Read the candidate's `kb.yaml`; record its exact ID, title, description,
   profile, version, and license.
2. Run `openshelf lint` against the candidate at the commit being
   registered. Do not register it if lint reports an error.
3. Add the candidate to `.openshelf/kbs.yaml` with a specific `use` hint,
   then run `openshelf sync --project .`. Sync must resolve the same ID as
   the manifest and regenerate `.openshelf/kbs.lock` and
   `.openshelf/context.md`.
4. Create its `wiki/` page as a `type: entity`, using the relevant topic as
   `category`; include the repository URL, status, `last_checked`, the KB ID,
   and the commit verified during registration.
5. Add the page to `index.md` and the catalogue in `README.md`.
6. Run `openshelf lint --strict .` and append a
   `## [YYYY-MM-DD] register | <title>` entry to `log.md`.

### update

When a registered KB changes materially, refresh its registry page and run
`openshelf sync --project .` so the lock and context move to the new commit.
Do not silently change a page's facts while updating its commit.

### retire

If a KB is retired, mark its registry page `status: archived` and explain
why. Remove it from `.openshelf/kbs.yaml` only when it should no longer be
offered as a connected KB; keep the page as the historical registry record.

### query

Read `index.md` first. Open a registry page only when its KB is in scope,
then follow that page to the member KB's own index and pages.

### lint

Run `openshelf lint --strict .`. Also check that `README.md`, `index.md`,
`wiki/`, and `.openshelf/kbs.yaml` name the same registered set.
