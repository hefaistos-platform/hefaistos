#!/usr/bin/env bash
set -Eeuo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
script="${root}/scripts/versioning.sh"
[[ "$(bash "${script}" select-version 1.9.0 1.8.13 patch)" == 1.9.0 ]]
[[ "$(bash "${script}" select-version 1.9.0 1.8.13 minor)" == 1.9.0 ]]
[[ "$(bash "${script}" select-version 1.8.13 1.8.13 minor)" == 1.9.0 ]]
[[ "$(bash "${script}" select-version 1.9.0 1.9.0 patch)" == 1.9.1 ]]
if bash "${script}" select-version 1.8.13 1.9.0 patch >/dev/null 2>&1; then
  echo 'Version rollback unexpectedly accepted' >&2
  exit 1
fi
echo 'Version selection tests passed.'
