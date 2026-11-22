"""Write synthetic offline fixtures in the transport.rest /locations and /journeys format.

The build sandbox could not reach the API, so these are hand-made scenarios (station IDs are
fake, names end in "(demo)"). Record real ones with:
  curl -G https://v6.db.transport.rest/journeys -d from=<ID> -d to=<ID> \
       -d national=false -d nationalExpress=false > fixtures/journeys.json
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

TZ = timezone(timedelta(hours=1))
DAY = datetime(2026, 11, 24, tzinfo=TZ)
A = {"type": "stop", "id": "900010", "name": "Jena Paradies (demo)"}
X = {"type": "stop", "id": "900011", "name": "Erfurt Hbf (demo)"}
B = {"type": "stop", "id": "900012", "name": "Göttingen (demo)"}


def t(hm: str, plus_min: int = 0) -> str:
    h, m = map(int, hm.split(":"))
    return (DAY + timedelta(hours=h, minutes=m + plus_min)).isoformat()


def leg(origin, dest, dep, arr, line, dep_delay=0, arr_delay=0, cancelled=False):
    leg = {
        "origin": origin,
        "destination": dest,
        "plannedDeparture": t(dep),
        "departure": None if cancelled else t(dep, dep_delay),
        "departureDelay": None if cancelled else dep_delay * 60,
        "plannedArrival": t(arr),
        "arrival": None if cancelled else t(arr, arr_delay),
        "arrivalDelay": None if cancelled else arr_delay * 60,
        "line": {"type": "line", "name": line, "product": "regional", "mode": "train"},
    }
    if cancelled:
        leg["cancelled"] = True
    return leg


def walk(at):
    return {
        "origin": at,
        "destination": at,
        "walking": True,
        "distance": 120,
        "departure": None,
        "arrival": None,
    }


journeys = [
    # tight: 6 planned minutes at Erfurt, first train 4 min late -> 2 min left
    [leg(A, X, "06:12", "06:58", "RE 3", 2, 4), walk(X), leg(X, B, "07:04", "08:52", "RE 2")],
    # first train cancelled
    [leg(A, X, "06:42", "07:28", "RB 20", cancelled=True), leg(X, B, "07:40", "09:30", "RE 2")],
    # comfortable 12 minute change
    [leg(A, X, "07:12", "07:58", "RE 3", 0, 1), leg(X, B, "08:10", "09:58", "RE 2", 0, 3)],
    # missed: 5 planned minutes, first train 9 min late
    [leg(A, X, "07:42", "08:28", "RB 20", 7, 9), leg(X, B, "08:33", "10:21", "RE 2")],
]
out = Path(__file__).parent
(out / "journeys.json").write_text(
    json.dumps({"journeys": [{"type": "journey", "legs": legs} for legs in journeys]}, indent=1)
)
(out / "locations.json").write_text(json.dumps([A, X, B], indent=1, ensure_ascii=False))
print("fixtures written")
