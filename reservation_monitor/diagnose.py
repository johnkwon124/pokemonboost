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


# Round one established that this is not about headers. Every shape sent to
# www.opentable.com -- including robots.txt, a static file every crawler on the
# internet fetches, and a bare HEAD -- was tarpitted for the full timeout, while
# example.com answered in 0.0s from the same runner. A block that catches
# robots.txt is keyed on the connecting IP, not on what the request looks like,
# so neither better headers nor a headless browser would change it.
#
# Round two asks a narrower question: is the block on the whole of OpenTable's
# infrastructure, or only on the www host? The mobile app and the regional sites
# sit behind different front doors, and any one of them answering would be
# enough to build on. Even a 404 counts as reachable here -- it means packets
# get through and only the path is wrong.
PROBES = [
    Probe("www (known tarpit)", "GET", "https://www.opentable.com/robots.txt", BROWSERLIKE),
    Probe("apex, no www", "GET", "https://opentable.com/robots.txt", BROWSERLIKE),
    Probe("mobile app API root", "GET", "https://mobile-api.opentable.com/", BROWSERLIKE),
    Probe("mobile app API, v1", "GET", "https://mobile-api.opentable.com/api/v1/", BROWSERLIKE),
    Probe("api host", "GET", "https://api.opentable.com/", BROWSERLIKE),
    Probe("platform host", "GET", "https://platform.opentable.com/", BROWSERLIKE),
    Probe("UK site", "GET", "https://www.opentable.co.uk/robots.txt", BROWSERLIKE),
    Probe("Canada site", "GET", "https://www.opentable.ca/robots.txt", BROWSERLIKE),
    # Control: proves the runner still has working egress.
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
