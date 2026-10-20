import http.client
import json
import time

import pytest

from valley.bench import RunSpec
from valley.live import LIVE_TAG, LiveServer, viewer_page
from valley.replay import FORMAT, read_replay

RULES = {"rabbit": "rules", "deer": "rules", "wolf": "rules"}


def make_server(tmp_path, days=1, pace=0.0, seed=19, **kwargs):
    spec = RunSpec(seed=seed, brains=RULES, experiment="live", days=days, log_requests=True)
    server = LiveServer(spec, str(tmp_path / "out"), port=0, pace=pace, out=lambda *a: None, **kwargs)
    server.start()
    return server


def open_stream(server):
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=30)
    conn.request("GET", "/stream")
    return conn, conn.getresponse()


def read_events(response, limit=None):
    """Yield (event, data) pairs from a Server-Sent Events response until it ends."""
    event, data, seen = None, [], 0
    while True:
        line = response.fp.readline()
        if not line:
            return
        line = line.decode("utf-8").rstrip("\n")
        if line.startswith(":"):
            continue
        if line == "":
            if event is not None:
                yield event, json.loads("\n".join(data))
                seen += 1
                if limit is not None and seen >= limit:
                    return
            event, data = None, []
        elif line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].strip())


@pytest.fixture
def servers():
    made = []
    yield made
    for server in made:
        server.close()


def test_the_viewer_page_is_given_the_stream_address():
    page = viewer_page()
    assert LIVE_TAG not in page and 'name="valley-live" content="/stream"' in page


def test_a_viewer_without_the_live_tag_is_rejected(tmp_path):
    bad = tmp_path / "index.html"
    bad.write_text("<html></html>")
    with pytest.raises(ValueError, match="valley-live"):
        viewer_page(bad)


def test_the_server_binds_to_localhost_only(tmp_path, servers):
    server = make_server(tmp_path)
    servers.append(server)
    assert server.httpd.server_address[0] == "127.0.0.1"


def test_the_server_serves_the_viewer_and_404s_elsewhere(tmp_path, servers):
    server = make_server(tmp_path)
    servers.append(server)
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=10)
    conn.request("GET", "/")
    response = conn.getresponse()
    body = response.read().decode()
    assert response.status == 200 and 'content="/stream"' in body and "three@0.160.0" in body
    conn.request("GET", "/missing")
    assert conn.getresponse().status == 404
    conn.close()
    server.stop()


def test_the_stream_sends_valid_frames_in_order_and_saves_a_matching_replay(tmp_path, servers):
    server = make_server(tmp_path, days=1)
    servers.append(server)
    conn, response = open_stream(server)
    assert response.status == 200 and response.getheader("Content-Type") == "text/event-stream"
    events = list(read_events(response))
    conn.close()

    kinds = [e for e, _ in events]
    assert kinds[0] == "meta" and kinds[-1] == "end" and set(kinds[1:-1]) == {"frame"}
    meta = events[0][1]
    assert meta["format"] == FORMAT and meta["meta"]["steps"] == 24 and meta["meta"]["seed"] == 19
    assert len(meta["frames"]) == 1 and meta["frames"][0]["step"] == 0
    assert len(meta["creatures"]) == 26

    frames = [data for kind, data in events if kind == "frame"]
    assert [f["step"] for f in frames] == list(range(1, 25))
    for f in frames:
        assert set(f) >= {"step", "agents", "carcasses", "events", "pop", "pace", "new_creatures", "notes", "fates"}
        assert set(f["pace"]) == {"seconds_this_hour", "hours_per_second"}
        assert f["pace"]["seconds_this_hour"] >= 0 and f["pace"]["hours_per_second"] > 0
        assert ("food" in f) != ("food_diff" in f)

    assert server.finished.wait(10)
    saved = read_replay(server.result["paths"]["replay"])
    assert saved["meta"]["run_id"] == "live-rules-seed19"
    extras = ("pace", "new_creatures", "notes", "fates")
    streamed = [meta["frames"][0]] + [{k: v for k, v in f.items() if k not in extras} for f in frames]
    assert streamed == saved["frames"]
    assert events[-1][1]["hours"] == 24 and events[-1][1]["saved"].endswith("replay.json")


def test_the_stream_carries_everything_the_viewer_needs_to_name_and_remember_animals(tmp_path, servers):
    server = make_server(tmp_path, days=3)
    servers.append(server)
    conn, response = open_stream(server)
    events = list(read_events(response))
    conn.close()
    assert server.finished.wait(10)
    saved = read_replay(server.result["paths"]["replay"])

    known = dict(events[0][1]["creatures"])
    notes = {cid: list(c["notes"]) for cid, c in known.items()}
    fates = {}
    for kind, data in events[1:]:
        if kind != "frame":
            continue
        known.update(data["new_creatures"])
        for cid, record in data["new_creatures"].items():
            notes.setdefault(cid, list(record["notes"]))
        for cid, added in data["notes"].items():
            notes[cid].extend(added)
        fates.update(data["fates"])
        for row in data["agents"]:
            assert row[0] in known, f"{row[0]} appears before the viewer is told who it is"

    assert set(known) == set(saved["creatures"])
    births = [cid for cid, c in saved["creatures"].items() if c["born"] > 0]
    assert births, "three days should include some births"
    for cid, record in saved["creatures"].items():
        assert notes[cid] == record["notes"], cid
        assert known[cid]["name"] == record["name"] and known[cid]["age0"] == record["age0"]
        if record["died"] is not None:
            assert fates[cid] == {"died": record["died"], "cause": record["cause"]}


def test_a_viewer_that_joins_late_receives_the_hours_it_missed(tmp_path, servers):
    server = make_server(tmp_path, days=1, pace=0.01, wait_for_viewer=False)
    servers.append(server)
    deadline = time.time() + 10
    while len(server._messages) < 6 and time.time() < deadline:
        time.sleep(0.01)
    conn, response = open_stream(server)
    events = list(read_events(response))
    conn.close()
    frames = [d for k, d in events if k == "frame"]
    assert events[0][0] == "meta" and [f["step"] for f in frames] == list(range(1, 25))


def test_the_valley_waits_for_a_viewer_before_it_starts(tmp_path, servers):
    server = make_server(tmp_path, days=1)
    servers.append(server)
    time.sleep(0.25)
    assert server.sim.step_no == 0 and not server.finished.is_set()
    conn, response = open_stream(server)
    assert list(read_events(response, limit=2))[0][0] == "meta"
    conn.close()


def test_closing_the_page_stops_the_run_and_saves_what_was_decided(tmp_path, servers):
    server = make_server(tmp_path, days=30, pace=0.02, disconnect_grace=0.3)
    servers.append(server)
    conn, response = open_stream(server)
    list(read_events(response, limit=5))  # the meta event and four hours
    response.close()  # a browser closing the tab closes its socket; the response object holds it open otherwise
    conn.close()
    assert server.finished.wait(15)
    assert server.error is None
    assert 4 <= server.sim.step_no < 720
    saved = read_replay(server.result["paths"]["replay"])
    assert len(saved["frames"]) == server.sim.step_no + 1
    assert (tmp_path / "out" / "metrics.json").exists()


def test_the_pace_is_a_minimum_gap_between_frames(tmp_path, servers):
    server = make_server(tmp_path, days=1, pace=0.1)
    servers.append(server)
    conn, response = open_stream(server)
    stamps = []
    for kind, data in read_events(response, limit=6):
        stamps.append(time.monotonic())
    conn.close()
    gaps = [b - a for a, b in zip(stamps[2:], stamps[3:])]
    assert gaps and all(g >= 0.08 for g in gaps)


def test_a_failing_brain_does_not_hang_the_stream(tmp_path, servers, monkeypatch):
    server = make_server(tmp_path, days=1, wait_for_viewer=True)
    servers.append(server)

    def boom(*args, **kwargs):
        raise RuntimeError("brain exploded")

    monkeypatch.setattr(server.sim, "step", boom)
    conn, response = open_stream(server)
    events = list(read_events(response))
    conn.close()
    assert [e for e, _ in events] == ["meta", "end"]
    assert isinstance(server.error, RuntimeError)


def test_requests_log_is_enabled_for_live_runs_by_default():
    from valley import cli
    args = cli.build_parser().parse_args(["live"])
    assert args.log_requests is True
    assert cli.build_parser().parse_args(["run"]).log_requests is False
    assert cli.build_parser().parse_args(["live", "--no-log-requests"]).log_requests is False
