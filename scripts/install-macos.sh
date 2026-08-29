#!/bin/bash
# Set the reservation monitor up to run on this Mac, on a timer, in the
# background. Safe to re-run: it replaces whatever it installed last time.
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.jkwon.reservation-monitor"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
ENV_DIR="${HOME}/.reservation-monitor"
ENV_FILE="${ENV_DIR}/env"
LOG="${HOME}/Library/Logs/reservation-monitor.log"
INTERVAL_SECONDS=900   # every 15 minutes

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
die() { printf '\n\033[31merror: %s\033[0m\n' "$*" >&2; exit 1; }

# --- 1. Python -------------------------------------------------------------

say "1/5  Checking Python"
command -v python3 >/dev/null 2>&1 || die "python3 not found. Run 'xcode-select --install', then try again."
python3 --version

say "     Creating a private virtualenv"
python3 -m venv "${REPO_DIR}/.venv" || die "could not create ${REPO_DIR}/.venv"
"${REPO_DIR}/.venv/bin/pip" install --quiet --upgrade pip
"${REPO_DIR}/.venv/bin/pip" install --quiet -r "${REPO_DIR}/requirements-monitor.txt" \
  || die "could not install dependencies"
echo "     ok"

# --- 2. Can this Mac actually reach OpenTable? -----------------------------
#
# The whole reason the monitor moved off GitHub Actions is that OpenTable
# tarpits datacenter IPs. Prove this machine is treated differently before
# installing a timer that would otherwise fail silently every 15 minutes.

say "2/5  Checking that this Mac can reach OpenTable"
if ! "${REPO_DIR}/.venv/bin/python" -m reservation_monitor diagnose --timeout 12; then
  die "the diagnostic could not run"
fi
printf '\nDid the two OpenTable lines above say REACHABLE? [y/N] '
read -r answer
case "$answer" in
  [yY]*) ;;
  *) die "OpenTable is not reachable from this machine either. Stopping before installing a timer that cannot work." ;;
esac

# --- 3. Gmail app password -------------------------------------------------

say "3/5  Gmail app password"
if [ -f "$ENV_FILE" ]; then
  echo "     ${ENV_FILE} already exists — keeping it."
  echo "     Delete that file and re-run this script to change the password."
else
  echo "     This is an app password, not your Google account password."
  echo "     Google Account -> Security -> 2-Step Verification -> App passwords."
  printf '     Paste the 16-character app password: '
  stty -echo; read -r app_password; stty echo; echo
  [ -n "$app_password" ] || die "no password entered"
  mkdir -p "$ENV_DIR"
  # Spaces are how Google displays it; the SMTP server does not want them.
  app_password="${app_password// /}"
  cat > "$ENV_FILE" <<ENVEOF
SMTP_USER=jkwon47@gmail.com
SMTP_PASSWORD=${app_password}
ENVEOF
  chmod 600 "$ENV_FILE"
  echo "     saved to ${ENV_FILE} (readable only by you)"
fi

# --- 4. Prove the mail path works before automating it ---------------------

say "4/5  Sending one test e-mail"
if "${REPO_DIR}/scripts/run-local.sh" test-email; then
  echo "     Check jkwon47@gmail.com — a test message should be waiting."
else
  die "the test e-mail failed. Fix the password in ${ENV_FILE} and re-run."
fi

# --- 5. The timer ----------------------------------------------------------

say "5/5  Installing the background timer"
mkdir -p "${HOME}/Library/LaunchAgents"
launchctl unload "$PLIST" 2>/dev/null
cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${REPO_DIR}/scripts/run-local.sh</string>
  </array>
  <key>StartInterval</key><integer>${INTERVAL_SECONDS}</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>${LOG}</string>
  <key>StandardErrorPath</key><string>${LOG}</string>
</dict>
</plist>
PLISTEOF
launchctl load "$PLIST" || die "launchctl could not load ${PLIST}"

say "Done."
cat <<DONE

The monitor now runs every $((INTERVAL_SECONDS / 60)) minutes in the background, and starts
again by itself whenever you log in.

  Watch it:     tail -f ${LOG}
  Run one now:  ${REPO_DIR}/scripts/run-local.sh
  Stop it:      launchctl unload ${PLIST}
  Start it:     launchctl load ${PLIST}

One thing left, and it matters: a sleeping Mac does not run timers. Open
System Settings -> Lock Screen and set "Turn display off on power adapter
when inactive", then System Settings -> Battery -> Options and turn on
"Prevent automatic sleeping on power adapter when the display is off".
Keep the Mac plugged in. Closing the lid still sleeps it on most models,
so leave it open, or connect an external display.

DONE
