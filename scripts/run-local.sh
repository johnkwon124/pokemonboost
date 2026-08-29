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
exec "${REPO_DIR}/.venv/bin/python" -m reservation_monitor "${1:-check}"
