"""dticket-commute: check a Deutschlandticket (regional-only) commute before leaving.

Exit codes: 0 = a safe connection exists, 1 = only risky ones, 2 = none usable.
That makes it easy to run from cron and alert only when needed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

from .assess import BROKEN, OK, RISKY, Assessment, assess, best
from .client import DEFAULT_BASE_URL, ApiClient, FixtureClient

EXIT = {OK: 0, RISKY: 1, BROKEN: 2}


def fmt(a: Assessment, marker: str = " ") -> str:
    head = (
        f"{marker} [{a.status:<6}] {a.departure:%H:%M} -> {a.arrival:%H:%M} "
        f"({a.duration_min:.0f} min, {len(a.lines) - 1} change(s), "
        f"arrival delay {a.arrival_delay_min:+.0f} min)  {' > '.join(a.lines)}"
    )
    details = [
        f"      change at {t.station}: {t.buffer_min:.0f} min (planned {t.planned_min:.0f})"
        for t in a.transfers
    ] + [f"      ! {p}" for p in a.problems]
    return "\n".join([head, *details])


def as_dict(a: Assessment) -> dict:
    return {
        "status": a.status,
        "departure": a.departure.isoformat(),
        "arrival": a.arrival.isoformat(),
        "arrival_delay_min": a.arrival_delay_min,
        "lines": a.lines,
        "transfers": [t.__dict__ for t in a.transfers],
        "problems": a.problems,
    }


def notify(url: str, text: str) -> None:
    """POST a plain-text message, e.g. to your own ntfy.sh topic or a chat webhook."""
    httpx.post(url, content=text.encode(), timeout=10).raise_for_status()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="dticket-commute",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("origin", help="station name or ID")
    p.add_argument("destination", help="station name or ID")
    p.add_argument("--departure", help="ISO time, e.g. 2026-11-24T06:30+01:00 (default: now)")
    p.add_argument("--results", type=int, default=4)
    p.add_argument("--min-transfer", type=float, default=5, help="minutes (default 5)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--notify-url", help="POST a summary here when no OK connection exists")
    p.add_argument("--fixtures", type=Path, help="use recorded API responses (offline)")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL)
    args = p.parse_args(argv)

    client = FixtureClient(args.fixtures) if args.fixtures else ApiClient(args.base_url)
    try:
        origin = client.find_station(args.origin)
        dest = client.find_station(args.destination)
        journeys = client.journeys(origin["id"], dest["id"], args.departure, args.results)
    except (LookupError, httpx.HTTPError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    results = [assess(j, args.min_transfer) for j in journeys]
    pick = best(results)
    status = pick.status if pick else BROKEN

    if args.json:
        print(
            json.dumps(
                {
                    "origin": origin,
                    "destination": dest,
                    "status": status,
                    "journeys": [as_dict(a) for a in results],
                },
                indent=2,
            )
        )
    else:
        print(f"{origin['name']} -> {dest['name']} (regional trains only)\n")
        for a in results:
            print(fmt(a, "*" if a is pick else " "))
        print(f"\nVerdict: {status}" + (f", best: {pick.departure:%H:%M}" if pick else ""))

    if args.notify_url and status != OK:
        summary = f"{origin['name']} -> {dest['name']}: {status}"
        if pick:
            summary += f". Best {pick.departure:%H:%M}->{pick.arrival:%H:%M}. " + "; ".join(
                pick.problems
            )
        notify(args.notify_url, summary)
    return EXIT[status]


if __name__ == "__main__":
    raise SystemExit(main())
