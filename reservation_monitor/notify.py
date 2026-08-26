"""E-mail delivery over SMTP (Gmail app passwords work as-is)."""

from __future__ import annotations

import datetime as dt
import os
import smtplib
from email.message import EmailMessage
from html import escape

from .config import MonitorConfig
from .models import Match


class NotifyError(RuntimeError):
    """SMTP was misconfigured or refused the message."""


class Mailer:
    def __init__(self, recipients: list[str]) -> None:
        self.recipients = recipients
        self.host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
        self.port = int(os.environ.get("SMTP_PORT", "587"))
        self.user = os.environ.get("SMTP_USER", "")
        self.password = os.environ.get("SMTP_PASSWORD", "")
        self.sender = os.environ.get("SMTP_FROM") or self.user
        self.dry_run = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")

    def send(self, subject: str, text: str, html: str | None = None) -> None:
        if self.dry_run:
            print(f"[dry-run] to={self.recipients} subject={subject}\n{text}")
            return
        if not self.user or not self.password:
            raise NotifyError(
                "SMTP_USER / SMTP_PASSWORD are not set. Add them as repository secrets "
                "(see docs/RESERVATION_MONITOR.md) or set DRY_RUN=1 to print instead."
            )
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.sender
        message["To"] = ", ".join(self.recipients)
        message.set_content(text)
        if html:
            message.add_alternative(html, subtype="html")
        try:
            with smtplib.SMTP(self.host, self.port, timeout=30) as smtp:
                smtp.starttls()
                smtp.login(self.user, self.password)
                smtp.send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            raise NotifyError(f"sending mail via {self.host}:{self.port} failed: {exc}") from exc


def availability_email(config: MonitorConfig, matches: list[Match]) -> tuple[str, str, str]:
    """Subject, plain-text body and HTML body for an availability alert."""
    venue = config.venue.name
    first = matches[0]
    if len(matches) == 1:
        subject = f"🍽️ {venue}: {first.slot.start.strftime('%a %b %-d %-I:%M %p')} open for {config.party_size}"
    else:
        subject = f"🍽️ {venue}: {len(matches)} slots open for {config.party_size}"

    lines = [
        f"{venue} has availability for {config.party_size}.",
        "",
    ]
    for match in matches:
        lines.append(f"  • {match.describe()}")
        if match.slot.booking_url:
            lines.append(f"    {match.slot.booking_url}")
    lines += [
        "",
        "Book fast — these get taken within minutes.",
        "",
        f"Watching: {', '.join(t.describe() for t in config.targets)}",
        f"Window:   {config.start_date} to {config.end_date}",
    ]
    if config.venue.url:
        lines.append(f"Venue:    {config.venue.url}")
    text = "\n".join(lines)

    rows = []
    for match in matches:
        link = match.slot.booking_url or config.venue.url
        label = escape(match.describe())
        badge = "" if match.exact else ' <span style="color:#8a6d3b">near match</span>'
        cell = f'<a href="{escape(link)}">{label}</a>' if link else label
        rows.append(f"<li style='margin:6px 0'>{cell}{badge}</li>")
    html = f"""<html><body style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#222">
<h2 style="margin:0 0 4px">{escape(venue)} — table for {config.party_size}</h2>
<p style="margin:0 0 12px;color:#666">Availability just appeared. These usually go fast.</p>
<ul style="padding-left:18px">{''.join(rows)}</ul>
<hr style="border:none;border-top:1px solid #eee;margin:16px 0">
<p style="font-size:12px;color:#888">
Watching {escape(', '.join(t.describe() for t in config.targets))}<br>
between {config.start_date} and {config.end_date}.
</p></body></html>"""
    return subject, text, html


def heartbeat_email(
    config: MonitorConfig, scanned_dates: int, slots_seen: int, now: dt.datetime
) -> tuple[str, str]:
    subject = f"✅ Reservation monitor alive — {config.venue.name}"
    text = "\n".join(
        [
            f"Daily check-in at {now.strftime('%Y-%m-%d %H:%M')} ({config.venue.timezone}).",
            "",
            f"Venue:      {config.venue.name} ({config.venue.provider})",
            f"Party size: {config.party_size}",
            f"Watching:   {', '.join(t.describe() for t in config.targets)}",
            f"Window:     {config.start_date} to {config.end_date}",
            "",
            f"Last scan checked {scanned_dates} candidate dates and saw {slots_seen} seatings",
            "of any kind. No matching slots yet — you'll get an e-mail the moment one shows up.",
        ]
    )
    return subject, text


def failure_email(config: MonitorConfig, failures: int, error: str) -> tuple[str, str]:
    subject = f"⚠️ Reservation monitor failing — {config.venue.name}"
    text = "\n".join(
        [
            f"The monitor has failed {failures} runs in a row, so it is probably not",
            "watching anything right now.",
            "",
            f"Latest error: {error}",
            "",
            "Most likely cause: the booking platform rotated its API key or token.",
            "See docs/RESERVATION_MONITOR.md for how to refresh the repository secret.",
        ]
    )
    return subject, text
