#!/usr/bin/env bash
# Shared helpers for the AWS fetchers (SOURCED, not executed).
#
# Credential + region resolution is the AWS CLI's job, via its own provider
# chain. The runner sets AWS_PROFILE / AWS_DEFAULT_REGION from a manifest target
# when one is given; when a target omits them — or there are no targets at all —
# they stay unset and the CLI uses the AMBIENT identity/region ("collect where
# deployed"). So fetchers do NOT pass --profile/--region; they just run `aws ...`
# and let the CLI read the env vars (or fall through to IRSA / instance role /
# SSO / ~/.aws). A profile-bearing target still scopes the run for fanout.
#
# Usage in a fetcher.sh:
#   source "$(dirname "$0")/../_shared/aws.sh"
#   _TARGET_ID="$(aws_target_id)"

# Recorded in evidence metadata only (the CLI reads the env itself). Empty is a
# valid value = ambient.
PROFILE="${AWS_PROFILE:-}"
REGION="${AWS_DEFAULT_REGION:-}"

# aws_target_id [REGION] — id for unique output filenames across a fanout: the
# profile when set, else "ambient", with the region appended only when passed.
# Regional fetchers pass "$REGION"; global fetchers (IAM, Route53, S3 naming)
# pass nothing so their filename stays account/profile-scoped. Account
# attribution always lives in the evidence metadata (account_id from
# `aws sts get-caller-identity`), so an ambient run is still traceable.
aws_target_id() {
  local id="${PROFILE:-ambient}"
  [ -n "${1:-}" ] && id="${id}_${1}"
  printf '%s' "$id" | tr -c 'A-Za-z0-9._-' '_'
}
