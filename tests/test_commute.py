import json
from pathlib import Path

import httpx
import pytest

from dticket_commute import cli
from dticket_commute.assess import BROKEN, OK, RISKY, assess, best
from dticket_commute.client import ApiClient, FixtureClient

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
JOURNEYS = json.loads((FIXTURES / "journeys.json").read_text())["journeys"]


def test_fixture_scenarios():
    statuses = [assess(j).status for j in JOURNEYS]
    assert statuses == [RISKY, BROKEN, OK, BROKEN]


def test_transfer_buffer_uses_realtime_and_skips_walking():
    a = assess(JOURNEYS[0])
    (t,) = a.transfers
    assert (t.buffer_min, t.planned_min) == (2, 6)
    assert a.lines == ["RE 3", "RE 2"]


def test_cancelled_leg_has_no_fake_transfer():
    a = assess(JOURNEYS[1])
    assert a.transfers == [] and "cancelled" in a.problems[0]


def test_min_transfer_threshold_is_configurable():
    assert assess(JOURNEYS[0], min_transfer=2).status == OK
    assert assess(JOURNEYS[2], min_transfer=15).status == RISKY


def test_non_dticket_product_is_flagged():
    j = json.loads(json.dumps(JOURNEYS[2]))
    j["legs"][1]["line"] = {"name": "IC 2153", "product": "national"}
    a = assess(j)
    assert a.status == BROKEN and "not covered" in a.problems[0]


def test_compensation_hint_after_60_minutes():
    j = json.loads(json.dumps(JOURNEYS[2]))
    j["legs"][-1]["arrivalDelay"] = 65 * 60
    assert any("compensation" in p for p in assess(j).problems)


def test_best_prefers_safe_then_earliest():
    assert best([assess(j) for j in JOURNEYS]).departure.strftime("%H:%M") == "07:12"
    assert best([]) is None


def test_api_client_requests_regional_only_and_resolves_station():
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req.url)
        if req.url.path == "/locations":
            return httpx.Response(200, json=[{"id": "8011956", "name": "Jena Paradies"}])
        return httpx.Response(200, json={"journeys": JOURNEYS})

    c = ApiClient(min_interval=0, http=httpx.Client(transport=httpx.MockTransport(handler)))
    assert c.find_station("Jena Paradies")["id"] == "8011956"
    assert c.find_station("8011956") == {"id": "8011956", "name": "8011956"}  # no request
    assert len(c.journeys("1", "2", None, 3)) == 4
    q = dict(calls[-1].params)
    assert q["national"] == "false" and q["nationalExpress"] == "false" and q["results"] == "3"
    assert len(calls) == 2


def test_fixture_client_station_lookup():
    assert FixtureClient(FIXTURES).find_station("göttingen")["id"] == "900012"
    with pytest.raises(LookupError):
        FixtureClient(FIXTURES).find_station("Clausthal")


def test_cli_exit_codes_and_json(capsys):
    args = ["Jena Paradies", "Göttingen", "--fixtures", str(FIXTURES)]
    assert cli.main(args) == 0
    assert "Verdict: OK, best: 07:12" in capsys.readouterr().out
    assert cli.main(args + ["--min-transfer", "15"]) == 1
    capsys.readouterr()
    assert cli.main(args + ["--json"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == OK
    assert cli.main(["Nowhere", "Göttingen", "--fixtures", str(FIXTURES)]) == 2


def test_notify_only_when_not_ok(monkeypatch):
    sent = []
    monkeypatch.setattr(cli, "notify", lambda url, text: sent.append((url, text)))
    base = ["Jena Paradies", "Göttingen", "--fixtures", str(FIXTURES), "--notify-url", "https://n"]
    cli.main(base)
    assert sent == []
    cli.main(base + ["--min-transfer", "15"])
    assert sent and sent[0][1].startswith("Jena Paradies (demo) -> Göttingen (demo): RISKY")
