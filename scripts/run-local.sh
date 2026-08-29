#!/bin/bash
# One scan. Invoked by launchd on a timer; also fine to run by hand.
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${HOME}/.reservation-monitor/env"

# Credentials live outside the repo, in a file only this user can read, so a
# public repository never sees them.
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
else
  echo "$(date '+%F %T') error: $ENV_FILE not found — run scripts/install-macos.sh" >&2
  exit 1
fi

cd "$REPO_DIR" || exit 1

# Pass every argument through, not just the first: `probe --dump raw.json`
# needs its flags. Set the default positionally rather than with "${@:-check}",
# which trips `set -u` on the bash 3.2 that ships with macOS.
if [ "$#" -eq 0 ]; then
  set -- check
fi
exec "${REPO_DIR}/.venv/bin/python" -m reservation_monitor "$@"
