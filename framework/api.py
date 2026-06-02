"""Facade for the fetcher framework — one source of truth for every front-end.

Both the CLI (`framework.runner`, driven by humans and AIs) and the web UI
(`framework.web`) call ONLY this module. They never re-implement discovery,
validation, manifest editing, or execution; they differ only in how they render
the JSON-able values these functions return.

Design constraints (see docs/config_injection_design.md, CLAUDE.md):
- The editable artifact is the manifest (customer-side values). Declarations
  (fetcher.yaml, fetchers/_categories/*.yaml) are read-only — they generate the
  form via catalog(); we never write into fetchers/.
- Secrets are references, never values. set_secret() writes ${env:VAR}; the form
  collects WHICH env var holds a secret, not the credential itself.

The in-memory manifest exchanged with callers is the raw dict ({"run": {...}}),
the same shape as the on-disk YAML and the manifest schema. Manifest is only
materialized internally (parse_manifest) for semantic validation and execution.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

from framework.config_loader import discover_fetchers, discover_platforms
from framework.contract import ConfigField, Secret, TargetField
from framework.envelope import wrap_outputs
from framework.runner import manifest_loader

_STDERR_TAIL_CHARS = 4000


# --------------------------------------------------------------------------- #
# Repo discovery
# --------------------------------------------------------------------------- #

def find_repo_root(start: Optional[Path] = None) -> Path:
    """Locate the repo root by walking up for sibling fetchers/ + framework/ dirs."""
    cur = (start or Path.cwd()).resolve()
    for parent in [cur, *cur.parents]:
        if (parent / "fetchers").is_dir() and (parent / "framework").is_dir():
            return parent
    raise RuntimeError(
        "Could not locate repo root (looking for sibling fetchers/ and framework/ dirs)"
    )


# --------------------------------------------------------------------------- #
# Catalog — discover + group + describe (powers the UI form and `catalog --json`)
# --------------------------------------------------------------------------- #

def _config_descriptor(f: ConfigField) -> dict:
    return {
        "name": f.name,
        "kind": "config",
        "type": f.type,
        "required": f.required,
        "default": f.default,
        "description": f.description,
        "env": f.env,
    }


def _secret_descriptor(s: Secret) -> dict:
    return {
        "name": s.name,
        "kind": "secret",
        "type": "string",
        "required": True,
        "default": None,
        "description": None,
        "env": s.env,
        "per_target": s.per_target,
    }


def _target_descriptor(f: TargetField) -> dict:
    return {
        "name": f.name,
        "kind": "target_field",
        "type": f.type,
        "required": f.required,
        "default": f.default,
        "description": f.description,
        "env": f.env,
    }


def _fetcher_descriptor(f) -> dict:
    return {
        "name": f.name,
        "version": f.version,
        "description": f.description,
        "category": f.category,
        "supports_targets": f.supports_targets,
        "config": [_config_descriptor(c) for c in f.config_schema.values()],
        "secrets": [_secret_descriptor(s) for s in f.secrets],
        "target_schema": [_target_descriptor(t) for t in f.target_schema.values()],
    }


def catalog(root: Path) -> dict:
    """Discover all fetchers, group them by category, and describe every editable
    field. This single structure is both the UI form schema and the AI-readable
    `catalog --json` output."""
    fetchers = discover_fetchers(root)
    platforms = discover_platforms(root)

    by_category: Dict[str, List[Any]] = {}
    for f in fetchers.values():
        by_category.setdefault(f.category or "_uncategorized", []).append(f)

    categories = []
    for name in sorted(by_category):
        spec = platforms.get(name)
        platform_block = None
        if spec is not None:
            platform_block = {
                "config": [_config_descriptor(c) for c in spec.config_schema.values()],
                "passthrough_env": list(spec.passthrough_env),
            }
        categories.append({
            "name": name,
            "description": spec.description if spec else None,
            "platform": platform_block,
            "fetchers": [
                _fetcher_descriptor(f)
                for f in sorted(by_category[name], key=lambda x: x.name)
            ],
        })

    return {"categories": categories, "fetcher_count": len(fetchers)}


# --------------------------------------------------------------------------- #
# Manifest read / write
# --------------------------------------------------------------------------- #

def read_manifest(path: Path) -> dict:
    """Read a manifest YAML into its raw dict. Returns an empty manifest if the
    file is missing or blank. Raises yaml.YAMLError on malformed YAML."""
    p = Path(path)
    if not p.exists():
        return init_manifest()
    data = yaml.safe_load(p.read_text())
    return data if isinstance(data, dict) else init_manifest()


def dump_manifest(manifest: dict, path: Path, root: Path) -> None:
    """Write a manifest dict to YAML. Refuses to write a structurally invalid
    (schema-invalid) manifest; semantic gaps (e.g. a not-yet-filled secret) are
    allowed so work-in-progress can be saved."""
    errs = manifest_loader.schema_errors(manifest, root)
    if errs:
        raise ValueError("refusing to write schema-invalid manifest:\n  " + "\n  ".join(errs))
    Path(path).write_text(yaml.safe_dump(manifest, sort_keys=False, default_flow_style=False))


# --------------------------------------------------------------------------- #
# Manifest mutation helpers (back the AI `manifest` subcommands and the UI PUT)
# All operate in place on the raw dict and return it for chaining.
# --------------------------------------------------------------------------- #

def init_manifest(output_dir: str = "./evidence") -> dict:
    return {"run": {"output_dir": output_dir, "fetchers": []}}


def _run(m: dict) -> dict:
    return m.setdefault("run", {})


def _entries(m: dict) -> list:
    return _run(m).setdefault("fetchers", [])


def _find_entry(m: dict, use: str) -> Optional[dict]:
    return next((e for e in _entries(m) if e.get("use") == use), None)


def _ensure_entry(m: dict, use: str) -> dict:
    entry = _find_entry(m, use)
    if entry is None:
        entry = {"use": use}
        _entries(m).append(entry)
    return entry


def set_output_dir(m: dict, output_dir: str) -> dict:
    _run(m)["output_dir"] = output_dir
    return m


def add_entry(m: dict, use: str) -> dict:
    if _find_entry(m, use) is None:
        _entries(m).append({"use": use})
    return m


def remove_entry(m: dict, use: str) -> dict:
    run = _run(m)
    run["fetchers"] = [e for e in _entries(m) if e.get("use") != use]
    return m


def set_fetcher_config(m: dict, use: str, key: str, value: Any) -> dict:
    _ensure_entry(m, use).setdefault("config", {})[key] = value
    return m


def set_secret(m: dict, use: str, name: str, env_var: str) -> dict:
    """Set a (non-per-target) secret reference for a fetcher entry. Stores a
    ${env:VAR} reference — never the secret value."""
    _ensure_entry(m, use).setdefault("secrets", {})[name] = f"${{env:{env_var}}}"
    return m


def add_target(
    m: dict, use: str, values: Dict[str, Any], secret_env: Optional[Dict[str, str]] = None
) -> dict:
    """Append a fanout target. secret_env maps per_target secret name -> ENV_VAR;
    each is stored as a ${env:VAR} reference."""
    entry = _ensure_entry(m, use)
    target = dict(values)
    if secret_env:
        target["secrets"] = {n: f"${{env:{v}}}" for n, v in secret_env.items()}
    entry.setdefault("targets", []).append(target)
    return m


def remove_target(m: dict, use: str, index: int) -> dict:
    """Remove the fanout target at `index` from a fetcher entry. No-op if the
    entry or index does not exist."""
    entry = _find_entry(m, use)
    if entry is not None:
        targets = entry.get("targets") or []
        if 0 <= index < len(targets):
            del targets[index]
    return m


def _platform(m: dict, category: str) -> dict:
    return _run(m).setdefault("platforms", {}).setdefault(category, {})


def set_platform_config(m: dict, category: str, key: str, value: Any) -> dict:
    _platform(m, category).setdefault("config", {})[key] = value
    return m


def set_passthrough_env(m: dict, category: str, env_vars: List[str]) -> dict:
    _platform(m, category).setdefault("auth", {})["passthrough_env"] = list(env_vars)
    return m


# --------------------------------------------------------------------------- #
# Validation — schema + semantic, returns readable error strings (never raises
# on a merely-incomplete manifest)
# --------------------------------------------------------------------------- #

def validate(manifest: dict, root: Path) -> List[str]:
    """Validate a manifest dict against the schema and the discovered fetchers.

    Returns a list of human-readable error strings (empty == valid+runnable).
    Mirrors the checks the runner enforces before executing.
    """
    errors = manifest_loader.schema_errors(manifest, root)
    if errors:
        return errors  # can't do semantic checks on a structurally-broken manifest

    fetchers = discover_fetchers(root)
    platforms = discover_platforms(root)
    parsed = manifest_loader.parse_manifest(manifest)

    for i, entry in enumerate(parsed.entries):
        if entry.use not in fetchers:
            errors.append(f"entry[{i}] uses unknown fetcher: {entry.use}")
            continue
        fetcher = fetchers[entry.use]

        if fetcher.supports_targets and not entry.targets:
            errors.append(f"{entry.use}: supports_targets but no targets[] in manifest")
        if not fetcher.supports_targets and entry.targets:
            errors.append(f"{entry.use}: does not support targets but manifest has targets[]")

        spec = platforms.get(fetcher.category)
        platform_cfg = parsed.platforms.get(fetcher.category)
        combined = {}
        if spec:
            combined.update(spec.config_schema)
        combined.update(fetcher.config_schema)
        for name, fdef in combined.items():
            if not fdef.required or fdef.default is not None:
                continue
            in_platform = platform_cfg and name in platform_cfg.config
            in_entry = name in entry.config
            if not (in_platform or in_entry):
                errors.append(
                    f"{entry.use}: required config '{name}' not set "
                    f"(platforms.{fetcher.category}.config or fetcher config)"
                )

        for secret in fetcher.secrets:
            if secret.per_target:
                for j, t in enumerate(entry.targets):
                    if secret.name not in t.secrets:
                        errors.append(
                            f"{entry.use} target[{j}] missing per_target secret '{secret.name}'"
                        )
            else:
                if secret.name not in entry.secrets:
                    errors.append(f"{entry.use}: missing secret '{secret.name}'")

    return errors


# --------------------------------------------------------------------------- #
# Run — the orchestration loop, with an optional event callback for streaming
# --------------------------------------------------------------------------- #

def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _invocation_record(r) -> dict:
    record = {
        "fetcher_name": r.fetcher_name,
        "fetcher_version": r.fetcher_version,
        "target": r.target,
        "started_at": r.started_at,
        "completed_at": r.completed_at,
        "duration_sec": r.duration_sec,
        "exit_code": r.exit_code,
        "outputs": r.outputs,
    }
    if r.exit_code != 0 and r.stderr:
        record["stderr_tail"] = r.stderr[-_STDERR_TAIL_CHARS:]
    return record


def run(
    manifest: dict,
    root: Path,
    on_event: Optional[Callable[[dict], None]] = None,
) -> dict:
    """Execute a manifest. Wraps each output in the evidence envelope and writes
    _run_metadata.json (unchanged from the original CLI run). Fires on_event for
    run_start / fetcher_start / fetcher_skip / log_line / fetcher_result /
    fetcher_error / run_complete so a UI can stream live progress.

    Returns a summary dict. Raises ValueError if the manifest is schema-invalid.
    """
    from framework.runner.executor import run_entry  # lazy: avoid import cycle

    errs = manifest_loader.schema_errors(manifest, root)
    if errs:
        raise ValueError("manifest schema invalid:\n  " + "\n  ".join(errs))

    fetchers = discover_fetchers(root)
    platforms = discover_platforms(root)
    parsed = manifest_loader.parse_manifest(manifest)

    def emit(event: dict) -> None:
        if on_event is not None:
            on_event(event)

    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    run_dir = parsed.output_dir.resolve() / f"run-{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)

    emit({
        "event": "run_start",
        "run_id": run_id,
        "run_dir": str(run_dir),
        "fetchers": [e.use for e in parsed.entries],
    })

    all_results = []
    overall_ok = True
    started_at = _iso_now()

    for entry in parsed.entries:
        if entry.use not in fetchers:
            emit({"event": "fetcher_skip", "fetcher": entry.use, "reason": "not discovered"})
            overall_ok = False
            continue
        fetcher = fetchers[entry.use]
        n_targets = len(entry.targets) if fetcher.supports_targets else 1
        emit({
            "event": "fetcher_start",
            "fetcher": entry.use,
            "targets": n_targets,
            "fanout": fetcher.supports_targets,
        })

        def on_line(line: str, _use=entry.use) -> None:
            emit({"event": "log_line", "fetcher": _use, "line": line})

        try:
            results = run_entry(
                fetcher,
                entry,
                run_dir,
                platforms.get(fetcher.category),
                parsed.platforms.get(fetcher.category),
                on_line=on_line,
            )
        except (RuntimeError, ValueError) as e:
            emit({"event": "fetcher_error", "fetcher": entry.use, "error": str(e)})
            overall_ok = False
            continue

        for r in results:
            wrap_outputs(r, fetcher, run_id, run_dir)
            if r.exit_code != 0:
                overall_ok = False
            emit({
                "event": "fetcher_result",
                "fetcher": entry.use,
                "exit_code": r.exit_code,
                "duration_sec": r.duration_sec,
                "target": r.target,
                "outputs": r.outputs,
            })
        all_results.extend(results)

    completed_at = _iso_now()
    metadata = {
        "run_id": run_id,
        "started_at": started_at,
        "completed_at": completed_at,
        "invocations": [_invocation_record(r) for r in all_results],
    }
    metadata_path = run_dir / "_run_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2, default=str))

    summary = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "metadata_path": str(metadata_path),
        "ok": overall_ok,
        "started_at": started_at,
        "completed_at": completed_at,
        "invocations": metadata["invocations"],
    }
    emit({"event": "run_complete", **summary})
    return summary
