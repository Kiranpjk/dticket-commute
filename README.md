# dticket-commute

[![CI](https://github.com/Kiranpjk/dticket-commute/actions/workflows/ci.yml/badge.svg)](https://github.com/Kiranpjk/dticket-commute/actions/workflows/ci.yml)
[![Docker](https://github.com/Kiranpjk/dticket-commute/actions/workflows/docker.yml/badge.svg)](https://github.com/Kiranpjk/dticket-commute/actions/workflows/docker.yml)

A CLI that checks your **Deutschlandticket commute** before you leave home. It asks the public
`v6.db.transport.rest` API for regional-only connections (no ICE/IC/EC), applies real-time
delays to every change, and gives each option a verdict:

- `OK`: all legs run and every change has at least `--min-transfer` minutes
- `RISKY`: a change is tighter than that because of delays
- `BROKEN`: a leg is cancelled, a connection is already missed, or a leg is not covered by the ticket

The exit code (0/1/2) and an optional webhook make it easy to run from cron and only get pinged
when your usual train is in trouble.

## Problem

With a Deutschlandticket you cannot fall back to an IC when a regional train is late. The DB
app shows each delay, but you still have to work out yourself whether the 6-minute change in
Erfurt still works, every morning, for several possible departures.

Source: r/transit, <https://www.reddit.com/r/transit/comments/177yh9r/>. Commenters discuss
how chronic delays have turned German rail commuting into a daily frustration.

## Architecture

```
station names --/locations--> IDs --/journeys?national=false&nationalExpress=false--> journeys
journeys --assess.py--> per option: real transfer buffers, cancellations, product check
         --best()-->    least risky, then earliest arrival
         --cli.py-->    text / JSON, exit code, optional POST to your webhook (e.g. ntfy)
```

| File | Purpose |
| --- | --- |
| `client.py` | `ApiClient` (at most 1 request/s, User-Agent, regional-only filter), `FixtureClient` for offline runs |
| `assess.py` | Transfer buffers from real-time times (planned as fallback), walking legs skipped, cancelled legs, non-D-Ticket products, 60-minute compensation hint |
| `cli.py` | Arguments, output, exit codes, notifications |

The compensation hint follows DB's Deutschlandticket FAQ
(<https://int.bahn.de/en/faq/deutschlandticket-compensation>): EUR 1.50 when you reach your
destination at least 60 minutes late, with claims under EUR 4 not paid out. You can bundle
several claims to reach that.

### Respecting the API

The community-run API asks for fewer than 100 requests per minute. One check makes 3
requests (two station lookups and one journey search, or one if you pass station IDs), spaced
at least 1 s apart. Schedule it every few minutes at most. There is no scraping and no login.

## Demo

The build sandbox could not reach the live API, so the demo uses **synthetic fixtures** in
the API's response format (`fixtures/make_fixtures.py`, fake station IDs, names marked
"(demo)"). They contain four scenarios: a tight change, a cancellation, a comfortable
connection and a missed connection. Output from a local run:

```
$ dticket-commute "Jena Paradies" "Göttingen" --fixtures fixtures; echo "exit=$?"
Jena Paradies (demo) -> Göttingen (demo) (regional trains only)

  [RISKY ] 06:14 -> 08:52 (158 min, 1 change(s), arrival delay +0 min)  RE 3 > RE 2
      change at Erfurt Hbf (demo): 2 min (planned 6)
      ! only 2 min to change at Erfurt Hbf (demo)
  [BROKEN] 06:42 -> 09:30 (168 min, 1 change(s), arrival delay +0 min)  RB 20 > RE 2
      ! RB 20 from Jena Paradies (demo) is cancelled
* [OK    ] 07:12 -> 10:01 (169 min, 1 change(s), arrival delay +3 min)  RE 3 > RE 2
      change at Erfurt Hbf (demo): 11 min (planned 12)
  [BROKEN] 07:49 -> 10:21 (152 min, 1 change(s), arrival delay +0 min)  RB 20 > RE 2
      change at Erfurt Hbf (demo): -4 min (planned 5)
      ! connection at Erfurt Hbf (demo) missed (-4 min)

Verdict: OK, best: 07:12
exit=0

$ dticket-commute "Jena Paradies" "Göttingen" --fixtures fixtures --min-transfer 15 >/dev/null; echo "exit=$?"
exit=1
```

## Usage

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"

dticket-commute "Jena Paradies" "Göttingen"                      # live, departing now
dticket-commute <FROM_ID> <TO_ID> --departure 2026-11-24T06:30+01:00 --min-transfer 7 --json
```

Weekday cron job that pings your phone through your own ntfy topic only when needed:

```cron
# m  h  dom mon dow
45   5  *   *   1-5  dticket-commute "<home station>" "<uni station>" --notify-url https://ntfy.sh/<your-topic>
```

## Run with Docker

```bash
docker build -t dticket-commute .
docker run --rm dticket-commute "Jena Paradies" "Göttingen" --fixtures /app/fixtures
docker run --rm dticket-commute "Jena Paradies" "Göttingen"     # live API
```

Image published by CI: `ghcr.io/kiranpjk/dticket-commute`.

## Tests

```bash
pytest -q   # 11 tests: verdicts for each scenario, real-time buffers, walking legs,
            # cancellations, product check, compensation hint, ranking, request params
            # (mocked HTTP), CLI exit codes, JSON output, notify-only-when-needed
```

## CI/CD

- `.github/workflows/ci.yml`: ruff lint + format check and pytest on Python 3.11 to 3.13.
- `.github/workflows/docker.yml`: builds on PRs; pushes to GHCR on `main` and `v*` tags with
  `GITHUB_TOKEN`.
- `.github/dependabot.yml`: weekly pip, Actions and Docker updates.

## Limitations

- "Regional only" relies on the API's product filter. A few regional lines need a
  supplement or do not accept the ticket, and the tool cannot know those exceptions.
- Fixture station IDs are fake. To pass IDs instead of names,
  look them up with `curl 'https://v6.db.transport.rest/locations?query=<name>'`.

## License

MIT, see [LICENSE](LICENSE).
