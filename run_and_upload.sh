#!/usr/bin/env bash
#
# Customer orchestration glue: collect evidence (runner) then upload it (uploader).
# The framework keeps these as SEPARATE stages on purpose; this script just chains
# them — the kind of thing that lives in your CI job / cron, not in the framework.
#
# Secrets must already be in the environment before running (never put values here):
#   KNOWBE4_API_KEY, KNOWBE4_REGION   — for collection
#   PARAMIFY_UPLOAD_API_TOKEN         — for upload
#
# Config (non-secret) is set here / overridable via env:
#   MANIFEST                 (default: manifest.yaml)
#   PARAMIFY_API_BASE_URL    (default: stage)

set -uo pipefail
cd "$(dirname "$0")"   # repo root

MANIFEST="${MANIFEST:-manifest.yaml}"
export PARAMIFY_API_BASE_URL="${PARAMIFY_API_BASE_URL:-https://stage.paramify.com/api/v0}"

echo "==> collect: $MANIFEST"
# Requires the package installed in the venv: pip install -e .
.venv/bin/paramify run "$MANIFEST"
collect_rc=$?
if [ $collect_rc -ne 0 ]; then
    echo "WARN: collect exited $collect_rc (a fetcher reported failures); uploading whatever was produced" >&2
fi

echo "==> upload: $PARAMIFY_API_BASE_URL (latest run)"
.venv/bin/python uploaders/paramify_evidence/uploader.py
