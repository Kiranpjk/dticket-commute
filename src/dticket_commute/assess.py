"""Turn raw journeys into a verdict: OK, RISKY (tight transfer) or BROKEN (missed/cancelled)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .client import DTICKET_PRODUCTS

OK, RISKY, BROKEN = "OK", "RISKY", "BROKEN"
SEVERITY = {OK: 0, RISKY: 1, BROKEN: 2}


@dataclass
class Transfer:
    station: str
    buffer_min: float  # real (delay-adjusted) time between arrival and next departure
    planned_min: float


@dataclass
class Assessment:
    status: str
    departure: datetime
    arrival: datetime
    arrival_delay_min: float
    lines: list[str]
    transfers: list[Transfer] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def duration_min(self) -> float:
        return (self.arrival - self.departure).total_seconds() / 60


def _ts(leg: dict, key: str) -> datetime | None:
    """Prefer the real-time value, fall back to the planned one."""
    value = leg.get(key) or leg.get("planned" + key[0].upper() + key[1:])
    return datetime.fromisoformat(value) if value else None


def _planned(leg: dict, key: str) -> datetime | None:
    value = leg.get("planned" + key[0].upper() + key[1:])
    return datetime.fromisoformat(value) if value else None


def assess(journey: dict, min_transfer: float = 5) -> Assessment:
    legs = [leg for leg in journey["legs"] if not leg.get("walking")] or journey["legs"]
    problems: list[str] = []
    status = OK

    def worsen(new: str, problem: str) -> None:
        nonlocal status
        problems.append(problem)
        if SEVERITY[new] > SEVERITY[status]:
            status = new

    for leg in legs:
        line = leg.get("line") or {}
        name = line.get("name", "?")
        if leg.get("cancelled"):
            worsen(BROKEN, f"{name} from {leg['origin']['name']} is cancelled")
        if line.get("product") and line["product"] not in DTICKET_PRODUCTS:
            worsen(BROKEN, f"{name} ({line['product']}) is not covered by the Deutschlandticket")

    transfers: list[Transfer] = []
    for prev, nxt in zip(legs, legs[1:], strict=False):
        arr, dep = _ts(prev, "arrival"), _ts(nxt, "departure")
        p_arr, p_dep = _planned(prev, "arrival"), _planned(nxt, "departure")
        if prev.get("cancelled") or nxt.get("cancelled") or not (arr and dep and p_arr and p_dep):
            continue
        t = Transfer(
            station=nxt["origin"]["name"],
            buffer_min=(dep - arr).total_seconds() / 60,
            planned_min=(p_dep - p_arr).total_seconds() / 60,
        )
        transfers.append(t)
        if t.buffer_min < 0:
            worsen(BROKEN, f"connection at {t.station} missed ({t.buffer_min:+.0f} min)")
        elif t.buffer_min < min_transfer:
            worsen(RISKY, f"only {t.buffer_min:.0f} min to change at {t.station}")

    first, last = legs[0], legs[-1]
    arr_delay = (last.get("arrivalDelay") or 0) / 60
    if arr_delay >= 60:
        problems.append(
            "arrival 60+ min late: you can claim EUR 1.50 Deutschlandticket compensation"
        )

    return Assessment(
        status=status,
        departure=_ts(first, "departure"),
        arrival=_ts(last, "arrival"),
        arrival_delay_min=arr_delay,
        lines=[(leg.get("line") or {}).get("name", "?") for leg in legs],
        transfers=transfers,
        problems=problems,
    )


def best(assessments: list[Assessment]) -> Assessment | None:
    """Earliest arrival among the least risky options."""
    if not assessments:
        return None
    return min(assessments, key=lambda a: (SEVERITY[a.status], a.arrival))
