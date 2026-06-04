# TUI design — a terminal front-end for paramify-fetchers

Status: **Phases 1–4 implemented** (`framework/tui/`: catalog browser, manifest
editor, run console, evidence browser). Remaining: the optional polish from
Phase 4 (Jump Mode, command palette, themes) is not yet built.

This document describes a Textual-based terminal UI for the framework, modeled
on the architecture of the [Bagels](https://github.com/EnhancedJax/Bagels)
expense-tracker TUI. It is a design + implementation plan, not a tutorial.

## 1. Why this maps cleanly

Bagels' whole design rests on one rule: **the UI talks only to its
`managers/*` layer, never to the database.** paramify-fetchers already enforces
the identical rule with `framework/api.py` — per `CLAUDE.md`, *"three front-ends
call ONLY `framework.api` so behavior is identical."* The human CLI
(`python -m framework.runner`), the AI `--json` CLI, and the FastAPI web UI
(`python -m framework.web`) all sit on that one facade.

**A TUI is simply front-end #4 over the same facade.** No domain logic, no
persistence, and no subprocess handling needs to be re-implemented — the TUI is
pure presentation. The web UI already proved the facade is GUI-sufficient: it
pipes `api.run()`'s `on_event` dicts through a thread+queue into a Server-Sent-
Events stream (`framework/web/server.py`). A Textual worker collapses that
bridge to a single `@work(thread=True)` call plus a message pump.

The enabling facts, all verified against `framework/api.py`:

- `api.catalog(root)` returns the form schema directly: categories → fetchers →
  typed field descriptors (`name / kind / type / required / default /
  description / env`). This is *both* the AI-readable catalog and the UI form
  spec (`api.py:104`).
- The in-place manifest mutators (`add_entry`, `remove_entry`,
  `set_fetcher_config`, `set_secret`, `add_target`, `set_platform_config`,
  `set_passthrough_env`, `set_output_dir`) do every edit and return the dict for
  chaining (`api.py:166-243`).
- `api.validate(manifest, root) -> List[str]` returns the human-readable
  "why won't this run" list; empty == runnable (`api.py:251`).
- `api.run(manifest, root, on_event=...)` streams a **closed vocabulary of
  seven events** to the callback: `run_start`, `fetcher_start`, `log_line`,
  `fetcher_result`, `fetcher_skip`, `fetcher_error`, `run_complete`
  (`api.py:331-437`).

**Verdict:** strongly recommended, low-to-moderate effort. A read-only catalog
browser is a few days (Phase 1, done); a full editor + run console + evidence
browser is a few weeks of part-time work, shippable in phases.

## 2. Architecture correspondence

| Bagels element | What it does | paramify-fetchers equivalent | Gap |
|---|---|---|---|
| `managers/*` — the only layer that opens DB sessions | Data-access layer; UI never touches SQLAlchemy | **`framework/api.py`** — `catalog` / mutators / `validate` / `run` | Exact role match. `api` mutates an in-memory dict; managers persist to SQLite per call. |
| `App` shell: header + `Tabs` + lazy body mount (`app.py`) | Thin shell routing between top-level views | `framework/tui/app.py` — `TabbedContent` with Catalog / Manifest / Run / Evidence panes | Direct port (we use idiomatic `TabbedContent` rather than the manual mount/remove dance). |
| Modules = `Static` with `compose()`-skeleton + `rebuild()`-data | Self-contained screen sections that re-query managers | Each page re-queries `api.catalog()` / re-renders the manifest dict | Direct port — the core recipe. |
| `forms/form.py` + `Fields`/`Field` (switch on `field.type`) | One generic widget renders any declarative form | `api`'s `_config_descriptor` / `_secret_descriptor` / `_target_descriptor` | **Highest-leverage reuse — `api` *already emits* the form spec; we build only the renderer.** |
| `modals/` confirmation + input, `dismiss(result)` → callback | Collect input → validate → return to caller | Add/edit-fetcher modal → `api.set_*`; confirm before remove/run | Direct port. |
| Jump Mode (`jumper.py`) + command palette (`provider.py`) | Single-key spatial nav; fuzzy cross-cutting actions | Jump between pages; `manifest: validate / run`, `theme: X` | Reimplement; cheap, high value. |
| vendored `DataTable` (~2,790 lines, group-header rows) | Data sink with typed row keys | **stock Textual `DataTable`** (or `Tree` for the category hierarchy) | Don't vendor — stock `DataTable`/`Tree` cover it. |
| `models/*` + SQLite, soft-delete, timestamps | ORM rows + engine | **none needed** — the "model" is the raw manifest dict + `fetcher.yaml` on disk | Gap that *helps*: nothing to build. |
| `tplot` / `barchart` / budgets / spinning donut | Terminal charts and finance widgets | **not applicable** | Drop entirely. |

## 3. Proposed screen architecture

The App owns shared state — `root` (from `api.find_repo_root()`),
`catalog_data` (cached `api.catalog(root)`), `manifest_path`, and the in-memory
`manifest` raw dict — and a top-level `rebuild()` that fans out to each page's
`rebuild()`, exactly as Bagels' `Home.rebuild()` fans out to its modules.

### 3.1 Catalog browser — `api.catalog(root)`  *(Phase 1, implemented)*

Left pane: a `Tree` of categories → fetchers with a live search `Input` filter.
Right pane: the selected fetcher's descriptor — `version`, `description`,
`supports_targets`, and three tables built from `config[]`, `secrets[]`,
`target_schema[]` (each descriptor's `name / type / required / default /
description / env`). Read-only.

```
┌─ paramify-fetchers ─────────────  Catalog · Manifest · Run · Evidence ────────┐
│ search: okta_                    │ okta_phishing_resistant_mfa          v0.3.0 │
│ ▾ aws            (30)            │ Collects phishing-resistant MFA enrollment… │
│ ▾ okta            (8)            │ targets: no   category: okta                │
│   okta_admin_mfa                 │ ── secrets ────────────────────────────────│
│ ▸ okta_phishing_resistant_mfa    │  OKTA_TOKEN    required   env OKTA_API_TOKEN │
│   okta_password_policy           │  OKTA_DOMAIN   required   env OKTA_DOMAIN    │
│ ▸ sentinelone     (5)            │ ── config ─────────────────────────────────│
│                                  │  (none)                                     │
└──[q]uit  [/]search  [r]efresh ───┴─────────────────────────────────────────────┘
```

### 3.2 Manifest editor — `api` mutators + `validate()`  *(Phase 2, implemented)*

The document is the raw manifest dict held in App state. The implemented page is
a `DataTable` of entries (fetcher · mode · secrets set/total · config set/total ·
targets · status) on the left, a live contract+values detail pane on the right,
and an `api.validate()` issues bar at the bottom. All editing goes through modals
→ `api` mutators → `rebuild()`: `a` add fetcher (filterable picker of fetchers not
yet in the manifest), `e` edit (a form generated from the descriptor — config
inputs + secret env-name inputs), `t`/`T` add/remove target, `x` remove entry
(confirm), `s` save, `v` validate, `p` YAML preview. The output-dir is an inline
input (committed on Enter). The original design (generated form per entry rendered
inline) is realized as an edit *modal* per entry to avoid focus-loss on partial
refresh — the same trade-off Bagels makes. Field → mutator bindings:

- `config[]` → typed inputs (Switch for `boolean`, restricted numeric `Input`
  for `integer`, text otherwise; `default` as placeholder) → `set_fetcher_config`.
- `secrets[]` → a text input holding the **env-var NAME** (never a value) →
  `set_secret` (which stores `${env:VAR}`). Adding a fetcher **auto-wires its
  entry-level secrets to the suggested env vars** (descriptor `env`), since the
  default is almost always correct — so a freshly added fetcher is immediately
  ✓ and the edit form is only needed to override a differing name. (Per-target
  secrets are not auto-wired: each target usually needs a distinct credential.)
- targets (if `supports_targets`) → a repeatable sub-form → `add_target`.
- output-dir → `set_output_dir`; platform config → `set_platform_config` /
  `set_passthrough_env`.

A live `api.validate()` "issues" panel gates the Run action; empty == runnable.
Writes go through the modal + `dismiss(result)` + callback + try/except +
`notify` + `rebuild` triad; removes/overwrites sit behind a `ConfirmationModal`.
Save = `api.dump_manifest()`, catching its `ValueError` so schema-invalid WIP is
reported but semantically-incomplete WIP can still be saved.

```
┌─ MANIFEST EDITOR ──  path: ./manifest.yaml   out: ./evidence ─────────────────┐
│ ┌ okta_phishing_resistant_mfa  [single]                              [x] ────┐ │
│ │ secrets:  OKTA_TOKEN  = [OKTA_API_TOKEN ] req                              │ │
│ │           OKTA_DOMAIN = [OKTA_DOMAIN    ] req                              │ │
│ └────────────────────────────────────────────────────────────────────────────┘ │
│ ┌ s3_encryption_status  [fanout]                                     [x] ────┐ │
│ │ targets: • region=us-east-1 profile=prod        [+ add target]            │ │
│ └────────────────────────────────────────────────────────────────────────────┘ │
│ ISSUES (validate): ✗ okta…: missing secret 'OKTA_DOMAIN'                        │
└──[a]dd  [s]ave  [v]alidate  [r]un ──────────────────────────────────────────────┘
```

### 3.3 Run console — `api.run(on_event=...)` on a Textual worker  *(Phase 3, implemented)*

A status `DataTable` (**one row per fetcher**, with fanout progress summarized in
an info column — `3/5 ok · 2 failed` — rather than per-target sub-rows, which keeps
the table stable since target identities only arrive with each `fetcher_result`),
plus a streaming `RichLog` that logs each stdout line *and* a per-target result
line, and a pass/fail/skip summary bar. Driven by the seven events on a
`@work(thread=True)` worker; the worker posts each event as a Textual message and
the UI-thread handler (`_handle_event`, kept worker-free so it's unit-testable)
applies it. Runs are gated on `api.validate()` (a confirm lets you run anyway) and
the Run control is disabled while a run is in flight. There is **no stop button** —
`api.run` has no cancel hook (the per-invocation 124 timeout is the only abort), so
offering one would mislead. State machine per row:

| event | effect |
|---|---|
| `run_start{fetchers[]}` | seed all rows QUEUED; show `run_dir` |
| `fetcher_start{fetcher, targets, fanout}` | mark RUNNING; expand into target sub-rows if `fanout` |
| `log_line{fetcher, line}` | append to `RichLog` (stdout only) |
| `fetcher_result{exit_code, duration_sec, target, outputs}` | OK if `exit_code==0`; `124`→TIMEOUT |
| `fetcher_skip{reason}` | SKIPPED |
| `fetcher_error{error}` | ERROR |
| `run_complete{ok, run_dir, metadata_path}` | footer banner; re-enable Run |

```
┌─ RUN CONSOLE ──────────────────────────  run-2026-06-02T14-03-11Z ────────────┐
│ summary: ██████ ok 4  ██ fail 1  ░ skip 0           [▶ run] [■ stop] [v]alidate│
│ ┌ STATUS ──────────────────────────┐ ┌ LOG ───────────────────────────────────┐│
│ │ FETCHER          TARGET   ST EXIT│  s3_encryption ▸ us-east-1: 18 buckets     ││
│ │ okta_phishing_mfa —       OK  0  │  s3_encryption ▸ eu-west-1: AccessDenied   ││
│ │ s3_encryption    us-east1 OK  0  │  knowbe4_training ▸ fetching campaigns…    ││
│ │ s3_encryption    eu-west1 FAIL 1 │                                            ││
│ └──────────────────────────────────┘ └────────────────────────────────────────┘│
│ done → ./evidence/run-…/_run_metadata.json   ok=false                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.4 Evidence browser  *(Phase 4, implemented)*

Two `DataTable`s: a **runs** picker (newest first — `run_id`, completed time, ok/
fail counts) and, for the selected run, its **output files** joined with their
invocation records (`fetcher`, `target`, exit code). Enter on a file opens a
detail modal showing the enveloped evidence — `metadata` (fetcher, status/exit,
`evidence_set` reference/name/instructions) + pretty-printed `payload` — or the
raw content for legacy/un-enveloped files. This is backed by **two new facade
functions** (see §6/§7): `api.list_runs(output_dir)` and `api.read_evidence(path)`,
so the TUI stays purely on `framework.api`. It's also a run-history view the web
UI lacks (re-lists on each visit, so a just-finished run shows up).

## 4. Data flow

The invariant matches Bagels: a UI module never touches the subprocess, the
filesystem, or `fetcher.yaml` directly — it calls `framework.api`.

- **Startup:** `root = api.find_repo_root()`; `catalog_data = api.catalog(root)`;
  `manifest = api.read_manifest(path)` (or `api.init_manifest()`). Cached in App
  state.
- **Browse / describe:** render `catalog` dicts directly — they are JSON-able.
- **Edit:** each form save handler maps 1:1 onto an in-place mutator.
- **Validate:** after each edit (debounced), `api.validate()`; gate Run on `[]`.
- **Persist:** `api.dump_manifest()`; catch `ValueError` (schema-invalid).

The run event protocol → Textual worker (the SSE analog):

```python
class RunEvent(Message):
    def __init__(self, ev: dict) -> None:
        self.ev = ev; super().__init__()

@work(thread=True, exclusive=True)
def _run_worker(self) -> None:
    api.run(self.manifest, self.root,
            on_event=lambda ev: self.post_message(RunEvent(ev)))

def on_run_event(self, message: RunEvent) -> None:   # back on the UI thread
    match message.ev["event"]:
        case "log_line":     self.query_one(RichLog).write(message.ev["line"])
        case "fetcher_result": ...   # OK / FAIL / 124→TIMEOUT
        case "run_complete": ...
```

`post_message` is thread-safe; Textual marshals back onto the UI thread, so the
web layer's manual queue + `_end` sentinel are unnecessary.

## 5. File layout

Mirrors `framework/web/`'s package shape and honors the "front-ends call ONLY
`framework.api`" rule — nothing under `tui/` imports `runner.executor`,
`manifest_loader`, or reads `fetcher.yaml` directly.

```
framework/tui/
├── __init__.py
├── __main__.py            # python -m framework.tui [--manifest PATH] [--at ROOT]
├── app.py                 # FetcherApp(App): TabbedContent, shared state, tab-focus
├── render.py              # Rich renderers: fetcher contract + manifest-entry detail
├── modals.py              # FormModal / PickerModal / ConfirmModal / PreviewModal  (Phase 2)
├── screens/
│   ├── catalog.py         # CatalogPage   — api.catalog(root)            (Phase 1)
│   ├── manifest.py        # ManifestPage  — api mutators + validate      (Phase 2)
│   ├── run.py             # RunPage       — api.run(on_event=...)         (Phase 3)
│   └── evidence.py        # EvidencePage  — api.list_runs/read_evidence  (Phase 4)
├── components/
│   └── forms.py           # FieldRow (switch on kind+type) + env_name_from_ref (Phase 2)
├── jumper.py              # (not yet built) Jump Mode overlay              (polish)
├── provider.py            # (not yet built) command palette                (polish)
└── styles/
    └── index.tcss
```

`framework/tui/__main__.py` deliberately parallels `framework/web/__main__.py`:
`python -m framework.tui` launches the app, mirroring `python -m framework.web`.

## 6. Dependencies & license

**Runtime dep:** `textual` (which pulls in `rich`). Bagels pins
`textual>=1.0,<2.0`; we pin the same to keep the Jump Mode / DataTable patterns
portable 1:1. Added to `requirements.txt` under a TUI section, matching how the
web deps are treated. Textual and Rich are MIT-licensed.

**Bagels code reuse — license:** Bagels is **GPL-3.0** (confirmed in its
`LICENSE`). GPL is copyleft — copying its source files would impose GPL on this
repo, which is not what a commercial product wants. **We reimplement the
patterns; we do not copy the code.** This is low-cost: the high-value pieces are
thin (the jump overlay is a small modal; the `Fields`/`Field` switch-on-type is
straightforward), and the heavyweight vendored `DataTable` is unnecessary —
stock Textual `DataTable`/`Tree` already provide row keys, zebra striping, and
`RowHighlighted`/`NodeHighlighted` messages. Bagels stays *design inspiration*
documented in comments, never derived source.

## 7. Gaps, risks, and what NOT to do

- **One small facade addition was needed for Phase 2.** The editor needs to
  remove a fanout target, but `api` only had `add_target`. Phase 2 added
  `api.remove_target(m, use, index)` — a tiny, in-place, no-op-on-missing mutator
  matching the existing helpers, keeping the TUI purely on the facade. (Worth
  mirroring into the `manifest` CLI subcommands later for parity; not required by
  the TUI.)
- **Evidence-browsing API (added) and no cancel hook.** Phase 4 took the
  facade-consistent route: two small additive functions, `api.list_runs(output_dir)`
  (summaries from each `run-*/_run_metadata.json` joined with output files) and
  `api.read_evidence(path)` (normalizes the envelope vs. a raw/legacy file), so
  the Evidence page never reads run dirs directly. Still no cancel hook — a "stop"
  button can `worker.cancel()` future entries but cannot kill an in-flight
  subprocess without an executor change — do **not** promise a hard cancel in v1.
- **`logger.py` / `retry.py` / `dependency_graph.py` are empty stubs** — no
  retries, no comparator `depends_on` DAG. Don't build retry/progress-bar UI.
- **Whole-manifest validation, not per-field.** `api.validate` returns strings
  naming the entry/field (e.g. `"<use>: missing secret '<name>'"`), not a
  field-keyed dict. Surface them in a global issues panel; don't over-engineer
  field-level error routing on day one. Note the two prefix conventions —
  `"<use>: …"` for known entries and `"entry[<i>] uses unknown fetcher: …"` for
  undiscovered ones — the editor buckets both to the right row.
- **`api.validate` does not check required *target* fields** (only required
  config and per-target secrets — `api.py`). A fanout target missing e.g.
  `region`/`profile` is flagged nowhere, so the editor can't rely on `validate()`
  for targets; it warns at add-target time instead. Adding required-target-field
  checks to `api.validate` is the proper fix, but it must account for global vs.
  regional AWS fetchers (global ones are profile-only, no `region`) — a framework
  change for all front-ends, out of scope for the TUI.
- **Bagels features that don't apply:** all plotting, budgets, the spinning
  donut, the finance modules, and the entire `models/` + SQLite layer. There is
  no DB — that's a simplification, not a gap.
- **Deferred — welcome `last run` is per-output-dir, not per-manifest.** The
  welcome picker's "last run" comes from `api.list_runs(<manifest output_dir>)`.
  Manifests that share an `output_dir` (e.g. the default `./evidence`) all show
  the *same* last run, because `_run_metadata.json` doesn't record which manifest
  produced a run. Proper fix: stamp the manifest name/path into the run metadata
  and filter `list_runs` by it. Cosmetic for now (a discovery-screen badge).
- **Deferred — exit 255 not a distinct run status.** The run console maps
  exit 0→OK, 124→TIMEOUT, non-zero→FAILED, and `fetcher_error`→ERROR
  (FAILED = ran and returned non-zero; ERROR = never ran). The framework
  synthesizes **exit 255** for a *per-target setup failure* in a fanout fetcher
  (e.g. a missing secret) — the same cause that is an ERROR for a single-target
  fetcher. Today 255 shows in the run *log* (labeled `setup-error`) but folds
  into FAILED in the status column. A small follow-up could give it a distinct
  `SETUP-ERR` status.

## 8. Phased implementation plan

Each phase is independently shippable and uses only `framework.api` (except the
optional Phase 4 evidence additions).

1. **Catalog browser** *(done)* — App shell + read-only browse. `api`:
   `find_repo_root`, `catalog`. Validates the whole shell and the
   "render descriptors directly" assumption.
2. **Manifest editor** *(done)* — entries table + per-entry edit modal
   (config + secret env-names), add/remove fetchers, add/remove fanout targets,
   inline output-dir, live `validate()` issues bar, YAML preview, save/load.
   `api`: `read_manifest`, `init_manifest`, `add_entry`, `remove_entry`,
   `set_fetcher_config`, `set_secret`, `add_target`, `remove_target` (new),
   `set_output_dir`, `validate`, `dump_manifest`. (Platform-config editing
   — `set_platform_config` / `set_passthrough_env` — is deferred to a follow-up;
   most categories' platform config is optional or has defaults.)
3. **Run console** *(done)* — per-fetcher status table + streaming log + pass/
   fail/skip summary on a Textual worker. `api`: `validate` (gate, with a
   run-anyway confirm), `run(on_event=...)`. Renders `124`→TIMEOUT,
   `255`→SETUP-ERROR, fanout as `k/N ok`; validate-before-run and
   disable-while-running guards; no stop button (no cancel hook in `api`).
4. **Evidence browser** *(done)* — runs picker + per-run output files + a detail
   modal (enveloped metadata/evidence_set/payload, or raw for legacy files), a
   run-history view the web UI lacks. Added `api.list_runs` / `api.read_evidence`
   to stay on the facade. *Polish still to do:* Jump Mode, command palette, themes.
