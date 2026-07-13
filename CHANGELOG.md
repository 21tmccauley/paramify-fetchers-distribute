# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/) applied
to the contract (see [`docs/versioning.md`](docs/versioning.md)). "The contract"
is the public API surface — the `fetcher.yaml` / category / manifest / envelope
schemas and the `paramify` CLI — not the internal code.

## [Unreleased]

## [0.3.0-rc.1] - 2026-07-13

The distributable-install release candidate: the tool now works without a
clone. No schema changes — the envelope `schema_version` stays `1.0` and the
`fetcher.yaml` / category / manifest contracts are untouched.

### Added

- **The overlay distribution model** (`docs/distribution_design.md`). Built-ins
  ship read-only inside the package (`framework/_bundled/`); user-created
  fetchers and overrides live in `$PARAMIFY_HOME/fetchers/` and shadow
  built-ins via an ordered search path (`$PARAMIFY_FETCHERS_PATH` → dev
  checkout → user dir → installed bundle). Upgrades never write to the user
  dir. The earlier workspace-sync design is preserved under `docs/deferred/`.
- `paramify create <category>/<name>` — scaffold a new fetcher into your user
  dir from the shipped template; `--category-file` also scaffolds the category
  file for a brand-new platform.
- `paramify customize <fetcher>` — copy-on-write override of a built-in, with
  a sidecar so `paramify doctor` can flag the override when the original
  changes upstream.
- `paramify doctor` gains a distribution section: tool version, install path,
  user dir, content roots, shadows, stale/orphaned overrides, and invalid
  fetchers.
- **The wheel is a real artifact**: schemas, the KSI reference, TUI styles,
  the uploader, and the full content bundle ship in it — `pipx install` works
  from a bare machine. A Homebrew tap formula template lives under
  `packaging/brew/`.

### Changed

- Discovery is refuse-don't-crash: a broken `fetcher.yaml` is skipped and
  reported instead of aborting every command; cross-root name collisions are
  reported as shadows, never resolved silently.
- Fetcher child processes get the running interpreter's `bin/` prepended to
  `PATH`, so venv-installed CLIs (e.g. a pipx-injected `checkov`) resolve.
- The TUI works without a checkout (installed mode); the missing-textual hint
  now gives correct pipx/pip commands.

## [0.2.1-beta] - 2026-07-10

### Changed

- The `deploy/` bundle is now **Docker-only** (Dockerfile + compose + cron) — a
  smaller, less prescriptive deployment footprint for public use.

### Removed

- The Kubernetes deployment manifests and the multi-account hub-and-spoke
  Terraform (`deploy/k8s/`). The Kubernetes *fetchers* (`fetchers/k8s/`) are
  unaffected.

### Fixed

- The containerized deploy no longer defaults evidence uploads to Paramify
  staging; it uses production (`app.paramify.com`), matching the uploader's own
  default.

## [0.2.0-beta] - 2026-07-10

First public release — a beta / pre-release. Pre-1.0, so the contract may still
change before 1.0 (see [`docs/versioning.md`](docs/versioning.md)).

### Added

- Fetcher framework: the `paramify` CLI (list · catalog · describe · manifests ·
  validate · run · runs · evidence · upload · manifest builder) plus the
  `paramify tui` front-end, both talking only to `framework.api`.
- `paramify doctor` — a preflight that checks the Python version, the external
  CLIs each category needs on `PATH`, and (given a manifest) whether its secret
  env vars are set.
- 108 fetchers across 8 categories (aws 79, okta 8, sentinelone 5, knowbe4 4,
  gitlab 3, k8s 3, rippling 3, checkov 2). The AWS category collects where
  deployed via the ambient credential chain, with optional per-target
  profile/region fanout.
- Evidence envelope (`{schema_version, metadata, payload}`, `schema_version`
  `1.0`) wrapped around every fetcher output by the runner.
- Paramify evidence uploader (`uploaders/paramify_evidence/`).
- A containerized deployment bundle (`deploy/`) — a Docker image + compose that
  runs the collector on a schedule and uploads, with secrets injected at run time
  (environment or AWS Secrets Manager).
- A credential-free demo (`demo_hello` fetcher + `examples/demo.yaml`) that emits
  synthetic evidence, so the whole collect → envelope pipeline runs with no cloud
  account.
- KSI metadata: an optional `ksis` array on `fetcher.yaml`, mappings populated
  for 89 fetchers, and `paramify ksi` — a FedRAMP 20x KSI coverage view over
  `api.ksi_coverage()`.
- Optional `validators` metadata on `fetcher.yaml` (regex checks over the
  evidence payload).
- Versioning & contract policy ([`docs/versioning.md`](docs/versioning.md)), this
  changelog, and the manual release runbook
  ([`docs/releasing.md`](docs/releasing.md)).

### Changed

- Licensed under GPL-3.0-only.
- Documentation rewritten for public consumption; the README leads with the TUI,
  then the AI-agent path, then the CLI.
- TUI restyled — border titles, status pills, denser controls, and hatched empty
  states.

[Unreleased]: https://github.com/paramify/paramify-fetchers/compare/v0.3.0-rc.1...HEAD
[0.3.0-rc.1]: https://github.com/paramify/paramify-fetchers/compare/v0.2.1-beta...v0.3.0-rc.1
[0.2.1-beta]: https://github.com/paramify/paramify-fetchers/compare/v0.2.0-beta...v0.2.1-beta
[0.2.0-beta]: https://github.com/paramify/paramify-fetchers/releases/tag/v0.2.0-beta
