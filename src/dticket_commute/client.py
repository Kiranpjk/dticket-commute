"""Small, polite client for the public transport.rest API (or offline fixtures)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

DEFAULT_BASE_URL = "https://v6.db.transport.rest"
USER_AGENT = "dticket-commute/0.1 (portfolio project; github.com/kiranpjk/dticket-commute)"

# Products a Deutschlandticket is valid on. ICE/IC/EC ("nationalExpress"/"national") are not.
DTICKET_PRODUCTS = {"regionalExpress", "regional", "suburban", "bus", "ferry", "subway", "tram"}
REGIONAL_ONLY = {"nationalExpress": "false", "national": "false", "taxi": "false"}


class ApiClient:
    def __init__(
        self, base_url=DEFAULT_BASE_URL, min_interval=1.0, http: httpx.Client | None = None
    ):
        self.base_url = base_url.rstrip("/")
        self.min_interval = min_interval  # API docs ask for < 100 req/min; we do <= 60
        self.http = http or httpx.Client(timeout=20, headers={"User-Agent": USER_AGENT})
        self._last = 0.0

    def get(self, path: str, params: dict) -> object:
        wait = self.min_interval - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        resp = self.http.get(f"{self.base_url}{path}", params=params)
        resp.raise_for_status()
        return resp.json()

    def find_station(self, query: str) -> dict:
        if query.isdigit():
            return {"id": query, "name": query}
        hits = self.get(
            "/locations", {"query": query, "results": "1", "addresses": "false", "poi": "false"}
        )
        if not hits:
            raise LookupError(f"no station found for {query!r}")
        return {"id": hits[0]["id"], "name": hits[0]["name"]}

    def journeys(self, from_id: str, to_id: str, departure: str | None, results: int) -> list[dict]:
        params = {
            "from": from_id,
            "to": to_id,
            "results": str(results),
            "stopovers": "false",
            **REGIONAL_ONLY,
        }
        if departure:
            params["departure"] = departure
        return self.get("/journeys", params)["journeys"]


class FixtureClient(ApiClient):
    """Serves `locations.json` and `journeys.json` from a directory instead of the network."""

    def __init__(self, directory: Path):
        self.dir = Path(directory)

    def get(self, path: str, params: dict) -> object:
        if path == "/locations":
            stations = json.loads((self.dir / "locations.json").read_text(encoding="utf-8"))
            q = params["query"].casefold()
            return [s for s in stations if q in s["name"].casefold()][: int(params["results"])]
        if path == "/journeys":
            return json.loads((self.dir / "journeys.json").read_text(encoding="utf-8"))
        raise FileNotFoundError(path)
