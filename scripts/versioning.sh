#!/usr/bin/env bash

set -Eeuo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/versioning.sh validate <version>
  scripts/versioning.sh bump <version> <major|minor|patch>
  scripts/versioning.sh detect-bump --range <git-range>
  scripts/versioning.sh sharp <base-version> <build-number>

Notes:
  - Conventional Commit subjects are used for bump detection.
  - Major bump triggers:
      * Any subject with "!" before ":" (for example: feat!: ...)
      * Any commit body containing "BREAKING CHANGE:"
  - Minor bump trigger:
      * Any subject starting with "feat:"
  - Everything else defaults to patch.
EOF
}

is_semver() {
  local value="${1:-}"
  [[ "${value}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]
}

validate_semver() {
  local version="${1:-}"
  if ! is_semver "${version}"; then
    echo "Invalid semantic version: ${version}" >&2
    exit 1
  fi
}

bump_version() {
  local version="$1"
  local bump="$2"
  local major minor patch

  validate_semver "${version}"
  IFS='.' read -r major minor patch <<< "${version}"

  case "${bump}" in
    major)
      major=$((major + 1))
      minor=0
      patch=0
      ;;
    minor)
      minor=$((minor + 1))
      patch=0
      ;;
    patch)
      patch=$((patch + 1))
      ;;
    *)
      echo "Unsupported bump type: ${bump}" >&2
      exit 1
      ;;
  esac

  printf '%s.%s.%s\n' "${major}" "${minor}" "${patch}"
}

detect_bump_from_text() {
  local subjects="$1"
  local bodies="$2"

  if printf '%s\n%s\n' "${subjects}" "${bodies}" | grep -Eiq 'BREAKING CHANGE:'; then
    echo "major"
    return
  fi

  if printf '%s\n' "${subjects}" | grep -Eiq '^[a-z]+(\([^)]+\))?!:'; then
    echo "major"
    return
  fi

  if printf '%s\n' "${subjects}" | grep -Eiq '^feat(\([^)]+\))?:'; then
    echo "minor"
    return
  fi

  echo "patch"
}

detect_bump_from_range() {
  local range="$1"
  local subjects bodies

  if [[ "${range}" == *".."* ]]; then
    subjects="$(git log --format='%s' "${range}" 2>/dev/null || true)"
    bodies="$(git log --format='%b' "${range}" 2>/dev/null || true)"
  else
    subjects="$(git log -1 --format='%s' "${range}" 2>/dev/null || true)"
    bodies="$(git log -1 --format='%b' "${range}" 2>/dev/null || true)"
  fi

  detect_bump_from_text "${subjects}" "${bodies}"
}

sharp_version() {
  local base_version="$1"
  local build_number="$2"

  validate_semver "${base_version}"
  if [[ ! "${build_number}" =~ ^[0-9]+$ ]]; then
    echo "Build number must be an integer: ${build_number}" >&2
    exit 1
  fi

  printf '%s-sharp.%s\n' "${base_version}" "${build_number}"
}

main() {
  local cmd="${1:-}"

  case "${cmd}" in
    validate)
      [[ $# -eq 2 ]] || { usage; exit 1; }
      validate_semver "$2"
      echo "$2"
      ;;
    bump)
      [[ $# -eq 3 ]] || { usage; exit 1; }
      bump_version "$2" "$3"
      ;;
    detect-bump)
      [[ $# -eq 3 && "$2" == "--range" ]] || { usage; exit 1; }
      detect_bump_from_range "$3"
      ;;
    sharp)
      [[ $# -eq 3 ]] || { usage; exit 1; }
      sharp_version "$2" "$3"
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"
