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


PROBES = [
    # Does anything at all come back from the host?
    Probe("robots.txt, minimal", "GET", "https://www.opentable.com/robots.txt", MINIMAL),
    Probe("robots.txt, browser-like", "GET", "https://www.opentable.com/robots.txt", BROWSERLIKE),
    # Is the whole site guarded, or only the restaurant page?
    Probe("home page, browser-like", "GET", "https://www.opentable.com/", BROWSERLIKE),
    # The page we actually need, both ways.
    Probe("venue page, minimal", "GET", "https://www.opentable.com/house-of-prime-rib", MINIMAL),
    Probe("venue page, browser-like", "GET", "https://www.opentable.com/house-of-prime-rib", BROWSERLIKE),
    Probe("venue page, HEAD", "HEAD", "https://www.opentable.com/house-of-prime-rib", BROWSERLIKE),
    # A control: somewhere unrelated, to prove the runner has egress at all.
    Probe("control (example.com)", "GET", "https://example.com/", BROWSERLIKE),
]

CHALLENGE_MARKERS = (
    "captcha", "cf-browser-verification", "Access Denied", "Reference #",
    "akamai", "_Incapsula_", "Request unsuccessful", "bot detection",
)


def run(timeout: float = 15.0) -> int:
    print(f"probing {len(PROBES)} request shapes, {timeout:.0f}s timeout each\n")
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
        verdict = "CHALLENGE" if marker else ("OK" if resp.ok else "BLOCKED")
        if resp.ok and not marker:
            reachable += 1
        print(
            f"  {probe.label:28s}  {verdict:10s} HTTP {resp.status_code} "
            f"{len(resp.content):>7d}B  {elapsed:5.1f}s"
            + (f"  marker={marker!r}" if marker else "")
            + (f"  server={resp.headers.get('Server')}" if resp.headers.get("Server") else "")
        )
        if marker or not resp.ok:
            snippet = " ".join(body[:300].split())
            print(f"      {snippet}")

    print(f"\n{reachable}/{len(PROBES)} shapes got a clean response")
    return 0
