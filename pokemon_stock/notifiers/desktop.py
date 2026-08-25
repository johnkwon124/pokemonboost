"""Best-effort native desktop notifications (macOS / Linux / Windows)."""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys

from pokemon_stock.notifiers.base import Alert, Notifier

log = logging.getLogger(__name__)


def _escape_applescript(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


class DesktopNotifier(Notifier):
    name = "desktop"

    def send(self, alert: Alert) -> None:
        # One-line body: every OS notification centre truncates anyway.
        body = alert.body.replace("\n", " · ")
        command = self._command(alert.title, body)
        if not command:
            log.debug("이 플랫폼에서는 데스크톱 알림을 지원하지 않습니다.")
            return
        try:
            subprocess.run(command, check=True, capture_output=True, timeout=10)
        except (OSError, subprocess.SubprocessError) as exc:
            log.warning("데스크톱 알림 실패: %s", exc)

    def _command(self, title: str, body: str) -> list[str] | None:
        if sys.platform == "darwin":
            script = (
                f'display notification "{_escape_applescript(body)}" '
                f'with title "{_escape_applescript(title)}" sound name "Glass"'
            )
            return ["osascript", "-e", script]
        if sys.platform.startswith("linux") and shutil.which("notify-send"):
            return ["notify-send", "--urgency=critical", title, body]
        if sys.platform.startswith("win") and shutil.which("powershell"):
            title, body = title.replace("'", "''"), body.replace("'", "''")
            script = (
                "[reflection.assembly]::LoadWithPartialName('System.Windows.Forms') > $null;"
                "$n = New-Object System.Windows.Forms.NotifyIcon;"
                "$n.Icon = [System.Drawing.SystemIcons]::Information;"
                "$n.Visible = $true;"
                f"$n.ShowBalloonTip(10000, '{title}', '{body}', 'Info');"
            )
            return ["powershell", "-NoProfile", "-Command", script]
        return None
