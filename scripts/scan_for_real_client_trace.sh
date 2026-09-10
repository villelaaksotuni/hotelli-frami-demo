#!/usr/bin/env bash
# scan_for_real_client_trace.sh
#
# Fail-closed scanner for real-client identifiers, addresses, PII and secrets.
#
# Reads its extended-regex patterns, one per line, from scripts/real_client_markers.txt
# (relative to the repo root). Blank lines and lines whose first non-space character is
# '#' are ignored. If that marker file is missing, unreadable, or yields zero usable
# patterns, the scan exits 2 and prints no success message — a scan with no patterns is
# the one failure mode that would silently certify a dirty tree as clean.
#
# Usage:
#   scripts/scan_for_real_client_trace.sh [path ...]
#
# With no arguments, scans the whole repo root. With one or more path arguments, scans
# only those paths — this lets any task verify just the files it touched.
#
# Exit codes:
#   0 - no marker matched
#   1 - one or more markers matched (matches are printed with file and line number)
#   2 - the marker file is missing, unreadable, or contains no usable patterns

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
MARKERS_FILE="${REPO_ROOT}/scripts/real_client_markers.txt"

if [ ! -f "${MARKERS_FILE}" ] || [ ! -r "${MARKERS_FILE}" ]; then
  echo "ERROR: marker file not found or unreadable: ${MARKERS_FILE}" >&2
  echo "Refusing to report a clean scan without a marker source. Exiting 2." >&2
  exit 2
fi

# Build the pattern list: strip blank lines and comment lines (first non-space char '#').
PATTERNS=()
while IFS= read -r line; do
  # Skip blank lines
  [ -z "${line// /}" ] && continue
  # Skip comment lines (first non-space char is '#')
  trimmed="${line#"${line%%[![:space:]]*}"}"
  [[ "${trimmed:0:1}" == "#" ]] && continue
  PATTERNS+=("${line}")
done < "${MARKERS_FILE}"

if [ "${#PATTERNS[@]}" -eq 0 ]; then
  echo "ERROR: marker file present but contains zero usable patterns: ${MARKERS_FILE}" >&2
  echo "Refusing to report a clean scan with an empty pattern list. Exiting 2." >&2
  exit 2
fi

# Determine scan targets: default to repo root when no arguments given.
if [ "$#" -eq 0 ]; then
  TARGETS=("${REPO_ROOT}")
else
  TARGETS=("$@")
fi

FOUND=0
for pattern in "${PATTERNS[@]}"; do
  if grep -rniE \
      --exclude-dir=.git \
      --exclude-dir=data \
      --exclude='real_client_markers.txt' \
      -- "${pattern}" \
      "${TARGETS[@]}" 2>/dev/null; then
    FOUND=1
  fi
done

if [ "${FOUND}" -ne 0 ]; then
  echo "FAIL: real-client trace found (see matches above)." >&2
  exit 1
fi

echo "OK: no known real-client markers found in: ${TARGETS[*]}"
exit 0
