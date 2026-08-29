"""Characterise how a host responds to us, when it responds at all.

The first live run against OpenTable neither connected-refused nor returned an
error page: it completed the TLS handshake and then said nothing until the read
timed out. That is what bot protection looks like from a datacenter IP, and the
distinction matters — a challenge page, a 403 and a tarpit each call for a
different fix. This tries a spread of request shapes and reports what each one
actually got back.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import requests

CHROME_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

MINIMAL = {"User-Agent": CHROME_UA, "Accept": "application/json"}

# The header set a real Chrome tab sends on a top-level navigation. Bot
# protection commonly keys on the Sec-Fetch-* and sec-ch-ua families, which a
# bare requests call never sends.
BROWSERLIKE = {
    "User-Agent": CHROME_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "sec-ch-ua": '"Chromium";v="126", "Not:A-Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "Connection": "keep-alive",
}


@dataclass
class Probe:
    label: str
    method: str
    url: str
    headers: dict


# What two rounds against OpenTable established, so it is not re-litigated:
#
#   * It is not about headers. Every shape sent to www.opentable.com was
#     tarpitted for the full timeout -- robots.txt, the static file every
#     crawler fetches, and a bare HEAD included -- while example.com answered
#     in 0.0s from the same runner.
#   * It is not about which front door. The apex, the UK and Canada sites all
#     tarpit too; mobile-api returns an Akamai "Access Denied"; api.opentable
#     .com will not even open a connection.
#
# A block that catches robots.txt is keyed on the connecting IP, so no header
# set and no headless browser would move it. What this command is now for is
# answering one question on whatever machine it runs on: can this host reach
# OpenTable at all? Run it before trusting a new machine to do the watching.
PROBES = [
    Probe("robots.txt", "GET", "https://www.opentable.com/robots.txt", BROWSERLIKE),
    Probe("venue page", "GET", "https://www.opentable.com/house-of-prime-rib", BROWSERLIKE),
    # Control: proves this machine has working egress, so a failure above is
    # OpenTable's decision rather than a broken network.
    Probe("control (example.com)", "GET", "https://example.com/", BROWSERLIKE),
]

CHALLENGE_MARKERS = (
    "captcha", "cf-browser-verification", "Access Denied", "Reference #",
    "akamai", "_Incapsula_", "Request unsuccessful", "bot detection",
)


def run(timeout: float = 15.0) -> int:
    print(f"probing {len(PROBES)} hosts, {timeout:.0f}s timeout each\n")
    reachable = 0
    for probe in PROBES:
        started = time.monotonic()
        try:
            resp = requests.request(
                probe.method, probe.url, headers=probe.headers, timeout=timeout,
                allow_redirects=True,
            )
        except requests.exceptions.ReadTimeout:
            print(f"  {probe.label:28s}  TARPIT     connected, no response in {timeout:.0f}s")
            continue
        except requests.exceptions.ConnectTimeout:
            print(f"  {probe.label:28s}  NO CONNECT could not open a connection")
            continue
        except requests.RequestException as exc:
            print(f"  {probe.label:28s}  ERROR      {type(exc).__name__}: {exc}")
            continue

        elapsed = time.monotonic() - started
        body = resp.text if probe.method != "HEAD" else ""
        marker = next((m for m in CHALLENGE_MARKERS if m.lower() in body.lower()), None)
        if marker:
            verdict = "CHALLENGE"
        elif resp.status_code in (401, 403, 429):
            verdict = "REFUSED"
        else:
            # Any other answer, 404 included, means packets got through.
            verdict = "REACHABLE"
            reachable += 1
        print(
            f"  {probe.label:28s}  {verdict:10s} HTTP {resp.status_code} "
            f"{len(resp.content):>7d}B  {elapsed:5.1f}s"
            + (f"  marker={marker!r}" if marker else "")
            + (f"  server={resp.headers.get('Server')}" if resp.headers.get("Server") else "")
        )
        if marker or resp.status_code >= 400:
            snippet = " ".join(body[:300].split())
            print(f"      {snippet}")

    print(f"\n{reachable}/{len(PROBES)} hosts are reachable at all")
    return 0
