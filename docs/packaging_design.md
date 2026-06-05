# Packaging — Design (`paramify package`)

**Status:** Proposed (not built). Prototype = the hand-rolled bundle in `deploy/`.
**Date:** 2026-06-05
**Solves:** building a deployable container today means hand-editing a Dockerfile
(system binaries) and `pyproject.toml` (Python libs), with **no detection** — a
fetcher's missing dependency surfaces at *run time* (`ModuleNotFoundError` /
`command not found`). And there's no way to produce a *minimal* per-deployment
image. This makes "a customer adds a fetcher" fragile (see
[`fetcher_contract.md`](fetcher_contract.md), [`design.md`](design.md), and the
`deploy/` bundle).

---

## What it is

One CLI command — `paramify package` — that reads a manifest, resolves the exact
fetchers it uses, **unions their declared dependencies**, and generates a minimal,
correct build context (Dockerfile + optional compose/k8s + `.env.example`),
optionally building the image.

Two enablers make it deterministic:
1. **Fetchers declare their dependencies** in `fetcher.yaml` (new schema fields).
2. The `framework.api` facade already maps **manifest → fetchers → declarations**,
   so the dependency set is a pure function of data we already expose — no script
   grepping, no guessing.

It is the productized form of the manual `deploy/` bundle: that hand-written
`Dockerfile` becomes the **template** this command fills.

---

## 1. Schema additions

On `fetcher.yaml` under `runtime` (both optional, additive — see
`framework/schemas/fetcher_schema.json`):

```yaml
runtime:
  type: python
  entry: fetcher.py
  python_requires: [boto3, "requests>=2.31"]   # PEP 508 specs (python runtime)
  system_requires: [aws, jq]                    # logical tool names (any runtime)
```

Also allowed at the **category** level (`fetchers/_categories/<cat>.yaml`) so
shared deps are declared once, not per fetcher:

```yaml
# aws.yaml
system_requires: [aws, jq]     # every AWS fetcher needs these
```

The effective dependency set for a fetcher = `category.system_requires`
∪ `fetcher.runtime.system_requires` (same for `python_requires`). The base
framework deps (`python-dotenv`, `requests`, `pyyaml`, `jsonschema`, `typer`,
plus `textual` for the TUI) are always installed via `pip install -e .` and are
not re-declared.

**Why declaration beats grepping the scripts:** the lone fetcher that mentions
`terraform` only *scans* Terraform source (Checkov) — it does **not** invoke the
binary. A grep would false-positive and install Terraform needlessly; a
declaration is the author's ground truth.

---

## 2. The command

```
paramify package <manifest> [options]
  --target docker|compose|k8s   what to emit (default: docker)
  --out DIR                     build-context output dir (default: ./build)
  --base-image IMG              base (default: python:3.12-slim)
  --source copy|clone[:<ref>]   COPY local tree (default) or clone a tag
  --build                       actually run `docker build` (needs Docker)
  --tag NAME                    image tag when --build
  --json                        machine-readable summary
```

Resolution flow (all from the facade):
```
manifest ──► fetchers in use ──► union(system_requires) ─► RUN lines (via recipe catalog)
                              └─► union(python_requires) ─► one pip install line
                              └─► union(declared secrets) ─► .env.example
        ──► render template ──► Dockerfile (+ compose / k8s / configmap) [+ build]
```

It prints (and `--json` emits) the resolved dependency set so a reviewer can see
exactly what's going into the image and why.

---

## 3. The install-recipe catalog (the one non-trivial piece)

`system_requires: [aws]` says *what*, not *how to install it*. So the generator
needs a project-maintained map from a logical tool name → an install snippet.
Proposed home: `framework/packaging/recipes.yaml` (data, not code — matches the
project's declarative ethos).

```yaml
jq:        { apt: jq }                       # most tools: a one-word apt package
git:       { apt: git }
checkov:   { pip: checkov }                  # pip-installable
aws:       { script: "<official v2 installer, arch-aware>" }   # bespoke
kubectl:   { script: "<release binary, arch-aware>" }
# default for an unknown name: apt-get install -y <name>
```

- **~90% of tools fall through to the apt default**; only cloud CLIs
  (`aws`, `az`, `gcloud`) and pinned binaries (`kubectl`) need bespoke `script`
  entries. This catalog is the artifact you maintain as fetchers adopt new tools.
- **Python deps need no catalog** — `python_requires` values are pip specs; the
  generator emits one `pip install` (or a generated `requirements.txt`).
- Recipes are **arch-aware** (x86_64 / aarch64), as the hand-written
  `deploy/Dockerfile` already is. The generator **batches** all `apt` packages
  into one `RUN` for layer efficiency.

---

## 4. Generated artifacts

- **`Dockerfile`** — base + batched apt + bespoke `script` recipes + `pip install`
  (base + unioned `python_requires`) + `COPY` (source) + entrypoint. A matching
  **`.dockerignore`** excludes `**/.env*` so secrets never enter image layers
  (see the lesson in `deploy/.dockerignore`).
- **`--target compose`** — a `docker-compose.yml` (run-once + scheduler), like the
  bundle.
- **`--target k8s`** — `CronJob` + ServiceAccount + a `ConfigMap`-mounted manifest
  (so *what's collected* changes without an image rebuild) + a `Secret`/ExternalSecret
  stub. IRSA annotation is the one line that differs from local.
- **`.env.example`** — generated from the manifest's **declared secrets** (the
  facade knows them), so customers get the exact var list. Secrets are injected at
  runtime, never baked (see `config_injection_design.md` — secrets are
  source-agnostic).

---

## 5. Keeping declarations honest — the lint

Declarations rot if nothing enforces them (someone adds `import boto3`, forgets to
declare it → back to runtime surprises). Pair the schema with a check, run in CI
(its own command or folded into `paramify validate`):

- **Python:** AST-scan each `fetcher.py` for top-level imports, drop stdlib, map
  import-name → distribution-name (e.g. `yaml` → `pyyaml`) via a small table /
  `importlib.metadata`, and flag anything not covered by base + `python_requires`.
- **Bash:** heuristically scan for command invocations and flag binaries used but
  not in `system_requires`. Necessarily best-effort (bash is hard to analyze) —
  treat as a warning, not a hard gate.

This makes the declarations trustworthy enough to build from.

---

## 6. Edge cases & decisions

- **Reproducibility / pinning** — for stable images, pin `python_requires`
  (`boto3==…`) and binary versions, or emit a lockfile. Beta may default to
  latest; flag the trade-off.
- **Source: COPY vs clone** — `COPY` the local tree (default, simple, includes
  local fetchers) vs clone a tag (reproducible, needs build-time repo access).
- **Manifest delivery** — baked into the image (docker target) vs a K8s
  `ConfigMap` (k8s target) so manifests change without a rebuild.
- **Shared vs per-fetcher Python env** — start with one shared env (union of
  deps). Per-fetcher venvs would isolate version conflicts but add weight; defer.
- **Minimal images** — because resolution is per-manifest, an Okta-only deployment
  installs no `aws`/`kubectl`/`checkov`. Smaller, faster, smaller attack surface.

---

## 7. What it unblocks / convergence

This one capability ties off several open threads:
- **Distribution** (see the deferred `project` note / `design.md`) — containerizing
  was already the chosen path; this makes the image *generated and minimal* instead
  of hand-maintained.
- **Customer-added fetchers** — adding a fetcher with new deps becomes "declare in
  `fetcher.yaml`, re-`package`," not a manual Dockerfile + pyproject edit with a
  runtime surprise.
- **The `system_requires` gap** previously noted for both packaging *and* the
  "new dependency" problem — same field, solved once.

---

## 8. Rollout (phased)

1. **Schema + backfill.** Add `python_requires`/`system_requires` to
   `fetcher_schema.json` + `category_schema.json` + `contract.py`/`config_loader.py`;
   backfill declarations onto the existing 58 fetchers from the known mapping
   (aws→`aws,jq`; k8s→`aws,kubectl,jq`; checkov→`checkov,git,jq`; other bash→`jq`;
   python fetchers→their imports). *(~½–1 day)*
2. **Recipe catalog + `paramify package --target docker`** generating a build
   context. *(~1–2 days + the catalog)*
3. **`compose` / `k8s` targets, `--build`, the dep lint.** *(~1–1½ days)*
4. **Later:** slim images, version pinning / lockfiles, per-fetcher venvs if needed.

**MVP (phases 1–2): ~3–4 days** for "declare deps → generate a minimal, correct
Dockerfile from a manifest."

---

## 9. Open questions

- Pinning policy (latest vs pinned vs lockfile) for v1.
- The import-name → package-name table for the Python lint (seed list + fallback).
- Whether `paramify package` with no manifest should target *all* discovered
  fetchers (a "kitchen-sink" image) as a convenience.
- Whether to keep the hand-written `deploy/` bundle as the canonical escape hatch
  once the generator exists (recommended: yes — it's the template and a debugging
  reference).

## Relationship to the manual bundle
`deploy/` (PR #7) is the prototype and stays as the reference template + escape
hatch. `paramify package` automates exactly what that bundle does by hand, driven
by the declared dependencies above.
