#!/usr/bin/env bash
# Per-module unittest runner. One process per tests/test_*.py so Tk
# teardown cannot abort the rest of the suite.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"
TIMEOUT_SECS="${TEST_MODULE_TIMEOUT:-120}"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "no python: $PYTHON" >&2
  exit 1
fi

use_xvfb=0
if command -v xvfb-run >/dev/null 2>&1; then
  use_xvfb=1
fi

shopt -s nullglob
modules=(tests/test_*.py)
shopt -u nullglob

if [[ ${#modules[@]} -eq 0 ]]; then
  echo "no tests/test_*.py modules" >&2
  exit 1
fi

pass=0
fail=0
declare -a names
declare -a results

echo "Battle Buddy tests — one process per module"
echo "python: $PYTHON"
echo "timeout: ${TIMEOUT_SECS}s"
echo

for path in "${modules[@]}"; do
  base="$(basename "$path" .py)"
  module="tests.${base}"
  work="$(mktemp -d "${TMPDIR:-/tmp}/bb-test-${base}.XXXXXX")"
  names+=("$module")

  env_home="$work"
  cmd=(timeout --preserve-status "$TIMEOUT_SECS" env "HOME=$env_home" "BATTLEBUDDY_HOME=$env_home" "$PYTHON" -m unittest "$module")
  if [[ "$use_xvfb" -eq 1 ]]; then
    cmd=(timeout --preserve-status "$TIMEOUT_SECS" env "HOME=$env_home" "BATTLEBUDDY_HOME=$env_home" xvfb-run -a "$PYTHON" -m unittest "$module")
  fi

  echo "── $module"
  if "${cmd[@]}"; then
    results+=("PASS")
    pass=$((pass + 1))
  else
    rc=$?
    if [[ "$rc" -eq 124 ]]; then
      results+=("TIMEOUT")
    else
      results+=("FAIL")
    fi
    fail=$((fail + 1))
  fi
  rm -rf "$work"
  echo
done

printf '%-36s %s\n' "MODULE" "RESULT"
printf '%-36s %s\n' "------" "------"
for i in "${!names[@]}"; do
  printf '%-36s %s\n' "${names[$i]}" "${results[$i]}"
done
echo
echo "passed: $pass  failed: $fail  modules: ${#modules[@]}"

if [[ "$fail" -gt 0 ]]; then
  exit 1
fi
exit 0
