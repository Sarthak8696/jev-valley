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
    assert len(meta["creatures"]) == 39

    frames = [data for kind, data in events if kind == "frame"]
    assert [f["step"] for f in frames] == list(range(1, 25))
    for f in frames:
        assert set(f) >= {"step", "agents", "carcasses", "events", "pop", "pace", "new_creatures", "notes", "fates",
                          "calls"}
        assert set(f["pace"]) == {"seconds_this_hour", "hours_per_second"}
        assert f["pace"]["seconds_this_hour"] >= 0 and f["pace"]["hours_per_second"] > 0
        assert ("food" in f) != ("food_diff" in f)

    assert server.finished.wait(10)
    saved = read_replay(server.result["paths"]["replay"])
    assert saved["meta"]["run_id"] == "live-rules-seed19"
    extras = ("pace", "new_creatures", "notes", "fates", "calls")
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
    assert "brain exploded" in events[-1][1]["error"] and events[-1][1]["saved"] is None
    assert server.result is None and not (tmp_path / "out" / "replay.json").exists()


def test_requests_log_is_enabled_for_live_runs_by_default():
    from valley import cli
    args = cli.build_parser().parse_args(["live"])
    assert args.log_requests is True
    assert cli.build_parser().parse_args(["run"]).log_requests is False
    assert cli.build_parser().parse_args(["live", "--no-log-requests"]).log_requests is False


def test_a_model_error_during_a_live_run_stops_it_tells_the_viewer_and_saves_nothing(tmp_path, servers):
    unreachable = "system-one@http://127.0.0.1:9#test-model"  # nothing listens on port 9
    spec = RunSpec(seed=19, brains={k: unreachable for k in ("rabbit", "deer", "wolf")}, experiment="live",
                   days=1, log_requests=True)
    server = LiveServer(spec, str(tmp_path / "out"), port=0, pace=0.0, out=lambda *a: None)
    servers.append(server)
    server.start()
    conn, response = open_stream(server)
    events = list(read_events(response))
    conn.close()
    assert [e for e, _ in events] == ["meta", "end"]  # not a single hour was played
    end = events[-1][1]
    assert "connection failed" in end["error"] and "step 1" in end["error"] and end["saved"] is None
    assert server.finished.wait(10) and server.result is None
    assert not (tmp_path / "out" / "replay.json").exists()
    assert (tmp_path / "out" / "requests.jsonl").exists()


def test_every_live_frame_carries_running_totals_of_model_calls(tmp_path, servers):
    server = make_server(tmp_path, days=1)
    servers.append(server)
    conn, response = open_stream(server)
    frames = [d for k, d in read_events(response) if k == "frame"]
    conn.close()
    calls = [f["calls"] for f in frames]
    assert all(set(c) == {"requests", "decisions", "input_tokens", "output_tokens", "retries"} for c in calls)
    assert all(c["requests"] == 0 for c in calls)  # the offline brain makes no API calls
    assert [c["decisions"] for c in calls] == sorted(c["decisions"] for c in calls)
    assert calls[-1]["decisions"] > calls[0]["decisions"] > 0


def test_a_model_brains_requests_and_tokens_show_up_in_the_totals(tmp_path):
    from tests.test_system_one import FakeTransport, answer, brain as model_brain, ok, request
    spec = RunSpec(seed=19, brains=RULES, experiment="live", days=1)
    server = LiveServer(spec, str(tmp_path / "out"), port=0, pace=0.0, out=lambda *a: None)
    try:
        t = FakeTransport(lambda body, n: ok({"action": answer()}, usage={"input_tokens": 120, "output_tokens": 9}))
        server.instances = [model_brain(t)]
        server.instances[0].decide([request()])
        server.instances[0].decide([request()])
        assert server._calls() == {"requests": 2, "decisions": 2, "input_tokens": 240, "output_tokens": 18, "retries": 0}
    finally:
        server.close()


def test_closing_a_server_that_was_never_started_does_not_hang(tmp_path):
    spec = RunSpec(seed=19, brains=RULES, experiment="live", days=1)
    server = LiveServer(spec, str(tmp_path / "out"), port=0, pace=0.0, out=lambda *a: None)
    started = time.time()
    server.close()
    assert time.time() - started < 5


# -- the valley only runs as far as the viewer is showing -------------------------------------------

def post_control(server, body, raw=False):
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=10)
    payload = body if raw else json.dumps(body)
    conn.request("POST", "/control", body=payload, headers={"Content-Type": "application/json"})
    status = conn.getresponse().status
    conn.close()
    return status


def steady_step(server, seconds=0.6):
    """The hour the valley has reached, once it has had time to move on if it was going to."""
    time.sleep(seconds)
    return server.sim.step_no


def test_a_paused_valley_makes_no_decisions_and_carries_on_when_resumed(tmp_path, servers):
    server = make_server(tmp_path, days=1)
    servers.append(server)
    server.set_control(True, 0.0)  # paused before any viewer has seen anything
    conn, response = open_stream(server)
    assert steady_step(server) == 0  # the stream is open, the valley is held
    assert steady_step(server) == 0 and server.paused
    server.set_control(False, 100.0)  # resumed, with the playhead far enough on that nothing holds the valley back
    events = list(read_events(response))
    assert [e for e, _ in events][-1] == "end" and server.sim.step_no == 24


def test_a_valley_never_runs_more_than_the_look_ahead_in_front_of_the_viewer(tmp_path, servers):
    from valley.live import LOOKAHEAD_HOURS
    server = make_server(tmp_path, days=1)
    servers.append(server)
    server.set_control(False, 0.0)  # a viewer at hour 0 that is not moving
    conn, response = open_stream(server)
    assert steady_step(server) == LOOKAHEAD_HOURS
    assert steady_step(server, 0.3) == LOOKAHEAD_HOURS  # and it stays there
    server.set_control(False, 10.0)
    assert steady_step(server) == 10 + LOOKAHEAD_HOURS
    server.set_control(False, 100.0)
    assert [e for e, _ in read_events(response)][-1] == "end"


def test_a_viewer_that_never_reports_is_not_held_back(tmp_path, servers):
    server = make_server(tmp_path, days=1)
    servers.append(server)
    conn, response = open_stream(server)
    assert [e for e, _ in read_events(response)][-1] == "end" and server.sim.step_no == 24


def test_the_viewer_can_pause_the_valley_over_http(tmp_path, servers):
    server = make_server(tmp_path, days=1, pace=0.05)
    servers.append(server)
    conn, response = open_stream(server)
    assert post_control(server, {"paused": True, "playhead": 1.0}) == 204
    paused_at = steady_step(server)
    assert paused_at < 24 and server.paused
    assert steady_step(server) == paused_at  # still
    assert post_control(server, {"paused": False, "playhead": 100.0}) == 204
    assert [e for e, _ in read_events(response)][-1] == "end"


@pytest.mark.parametrize("body", [
    "not json", "{}", '{"paused": "yes"}', '{"paused": 1}', '{"paused": false, "playhead": -1}',
    '{"paused": false, "playhead": "3"}', '{"paused": false, "playhead": true}', "[]", "",
])
def test_nonsense_control_messages_are_refused_and_change_nothing(tmp_path, servers, body):
    server = make_server(tmp_path, days=1)
    servers.append(server)
    assert post_control(server, body, raw=True) == 400
    assert server.paused is False and server._playhead is None
    server.stop()


def test_a_huge_control_message_is_refused(tmp_path, servers):
    server = make_server(tmp_path, days=1)
    servers.append(server)
    assert post_control(server, json.dumps({"paused": True, "padding": "x" * 5000}), raw=True) == 400
    assert server.paused is False
    server.stop()


def test_posting_anywhere_else_is_a_404(tmp_path, servers):
    server = make_server(tmp_path, days=1)
    servers.append(server)
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=10)
    conn.request("POST", "/stream", body="{}")
    assert conn.getresponse().status == 404
    conn.close()
    server.stop()


def test_closing_the_page_while_paused_still_ends_the_run(tmp_path, servers):
    server = make_server(tmp_path, days=1, disconnect_grace=0.2)
    servers.append(server)
    server.set_control(True, 0.0)
    conn, response = open_stream(server)
    assert steady_step(server, 0.3) == 0
    response.close()  # a browser closing the tab closes its socket; the response object holds it open otherwise
    conn.close()  # the viewer leaves while the valley is held
    assert server.finished.wait(15)  # noticed at the next keepalive, then the grace period
    assert server.sim.step_no == 0 and server.error is None


def test_a_plain_kill_stops_the_run_like_ctrl_c_and_saves_what_was_decided(tmp_path):
    import signal
    import subprocess
    import sys
    code = (
        "from valley.bench import RunSpec\n"
        "from valley.live import LiveServer\n"
        "spec = RunSpec(seed=19, brains={'rabbit': 'rules', 'deer': 'rules', 'wolf': 'rules'}, experiment='live', days=30, log_requests=True)\n"
        f"LiveServer(spec, {str(tmp_path / 'out')!r}, port=0, pace=0.02, wait_for_viewer=False).run()\n"
    )
    process = subprocess.Popen([sys.executable, "-u", "-c", code], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)  # -u: lines arrive as they are printed
    try:
        assert "Jev Valley live at" in process.stdout.readline()
        time.sleep(1.0)  # let some hours be decided
        process.send_signal(signal.SIGTERM)
        out, err = process.communicate(timeout=60)
    finally:
        if process.poll() is None:
            process.kill()
    assert process.returncode == 0, err
    assert "Stopping; saving what has been decided so far." in out and "saved " in out
    saved = read_replay(str(tmp_path / "out" / "replay.json"))
    assert 5 <= len(saved["frames"]) < 720
