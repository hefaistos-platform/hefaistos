#!/usr/bin/env bash

set -Eeuo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/generate_changelog.sh --title <title> --range <git-range> --output <path>

Examples:
  scripts/generate_changelog.sh --title v1.2.3 --range abc123..def456 --output Versions/v1.2.3/changelog.md
  scripts/generate_changelog.sh --title v1.2.3 --range def456 --output Versions/v1.2.3/changelog.md
EOF
}

title=""
commit_range=""
output_file=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --title)
      [[ $# -ge 2 ]] || { usage; exit 1; }
      title="$2"
      shift 2
      ;;
    --range)
      [[ $# -ge 2 ]] || { usage; exit 1; }
      commit_range="$2"
      shift 2
      ;;
    --output)
      [[ $# -ge 2 ]] || { usage; exit 1; }
      output_file="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

[[ -n "${title}" && -n "${commit_range}" && -n "${output_file}" ]] || {
  usage
  exit 1
}

subjects=()
if [[ "${commit_range}" == *".."* ]]; then
  while IFS= read -r line; do
    subjects+=("${line}")
  done < <(git log --no-merges --format='%s' "${commit_range}" 2>/dev/null || true)
else
  while IFS= read -r line; do
    subjects+=("${line}")
  done < <(git log --no-merges -1 --format='%s' "${commit_range}" 2>/dev/null || true)
fi

changes=()
fixes=()
removals=()

for subject in "${subjects[@]}"; do
  lower_subject="$(printf '%s' "${subject}" | tr '[:upper:]' '[:lower:]')"

  if printf '%s\n' "${lower_subject}" | grep -Eiq '^fix(\([^)]+\))?:'; then
    fixes+=("${subject}")
  elif printf '%s\n' "${lower_subject}" | grep -Eiq '^(remove|removal|delete|drop)(\([^)]+\))?:' \
    || printf '%s\n' "${lower_subject}" | grep -Eiq '(^|[[:space:]])(remove|removed|removes|delete|deleted|drop|dropped)([[:space:]]|$)' \
    || printf '%s\n' "${subject}" | grep -Eq '!:'
  then
    removals+=("${subject}")
  else
    changes+=("${subject}")
  fi
done

migration_files=()
if [[ "${commit_range}" == *".."* ]]; then
  while IFS= read -r file; do
    migration_files+=("${file}")
  done < <(git diff --name-only "${commit_range}" -- ':(glob)backend/**/migrations/*.py' 2>/dev/null || true)
else
  while IFS= read -r file; do
    migration_files+=("${file}")
  done < <(git diff-tree --no-commit-id --name-only -r "${commit_range}" -- ':(glob)backend/**/migrations/*.py' 2>/dev/null || true)
fi

mkdir -p "$(dirname "${output_file}")"

{
  echo "# ${title}"
  echo
  echo "_Generated on $(date -u +'%Y-%m-%d')_"
  echo
  echo "## Changes"
  if [[ ${#changes[@]} -eq 0 ]]; then
    echo "- None"
  else
    for item in "${changes[@]}"; do
      printf -- '- %s\n' "${item}"
    done
  fi
  echo
  echo "## Fixes"
  if [[ ${#fixes[@]} -eq 0 ]]; then
    echo "- None"
  else
    for item in "${fixes[@]}"; do
      printf -- '- %s\n' "${item}"
    done
  fi
  echo
  echo "## Removals"
  if [[ ${#removals[@]} -eq 0 ]]; then
    echo "- None"
  else
    for item in "${removals[@]}"; do
      printf -- '- %s\n' "${item}"
    done
  fi
  echo
  echo "## Database Migrations"
  if [[ ${#migration_files[@]} -eq 0 ]]; then
    echo "- None"
  else
    for migration in "${migration_files[@]}"; do
      printf -- '- %s\n' "${migration}"
    done
  fi
} > "${output_file}"
