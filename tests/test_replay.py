import json
from pathlib import Path
import os
import random

import pytest

from valley import cli
from valley.bench import RunSpec, brain_label, run_one
from tests.offline import make_offline_brain as make_brain
from valley.replay import (
    FORMAT, MAX_REPLAY_BYTES, build_replay, check_format, dumps, embed_in_viewer, food_grids, read_replay,
    write_replay,
)
from valley.simulation import Simulation
from valley.species import SPECIES


def finished_sim(seed=7, days=3, brain="rules"):
    b = make_brain(brain, seed)
    sim = Simulation(seed, {s: b for s in SPECIES}, days=days)
    foods = [list(sim.world.food)]
    sim.run(on_frame=lambda frame: foods.append(list(sim.world.food)))
    return sim, foods


def test_a_replay_round_trips_through_write_and_read(tmp_path):
    sim, _ = finished_sim()
    replay = build_replay(sim, "test-rules-seed7")
    path = tmp_path / "replay.json"
    size = write_replay(str(path), replay)
    assert size == os.path.getsize(path)
    assert read_replay(str(path)) == json.loads(dumps(replay))


def test_the_document_has_the_documented_shape():
    sim, _ = finished_sim()
    replay = build_replay(sim, "test-rules-seed7")
    assert replay["format"] == FORMAT == "jev-valley/replay@3"
    meta = replay["meta"]
    for key in ("run_id", "seed", "map_retries", "steps", "start_hour", "width", "height", "tiles", "brains",
                "hesitate_below", "actions", "version"):
        assert key in meta
    assert meta["run_id"] == "test-rules-seed7" and meta["seed"] == 7 and meta["steps"] == 72
    assert meta["start_hour"] == 6 and (meta["width"], meta["height"]) == (40, 26)
    assert len(meta["tiles"]) == 26 and all(len(row) == 40 for row in meta["tiles"])
    assert meta["brains"] == {"rabbit": "rules", "deer": "rules", "wolf": "rules"}
    assert meta["hesitate_below"] is None
    assert meta["actions"]["wolf"][0] == "hunt" and meta["actions"]["rabbit"][0] == "eat"
    assert replay["frames"][0]["step"] == 0 and len(replay["frames"]) == sim.step_no + 1
    first = next(iter(replay["creatures"].values()))
    assert set(first) == {"name", "species", "personality", "born", "died", "cause", "parents", "notes", "age0"}
    assert isinstance(replay["summary"], dict)


def test_creature_notes_and_fates_are_recorded():
    sim, _ = finished_sim(days=10)
    replay = build_replay(sim, "x")
    dead = [(cid, c) for cid, c in replay["creatures"].items() if c["died"] is not None]
    assert dead and all(c["cause"] in ("eaten", "starved", "thirst") for _, c in dead)
    noted = [c for c in replay["creatures"].values() if c["notes"]]
    assert noted
    for creature in noted:
        for step, text in creature["notes"]:
            assert isinstance(step, int) and text != "hesitated"


def test_food_diff_rebuilds_the_full_grid_for_every_frame():
    sim, foods = finished_sim(days=4)
    replay = json.loads(dumps(build_replay(sim, "x")))
    rebuilt = list(food_grids(replay))
    assert len(rebuilt) == len(foods) == len(replay["frames"])
    for step, (grid, truth) in enumerate(zip(rebuilt, foods)):
        assert grid == truth, f"plant grid differs at step {step}"


def test_full_grids_appear_every_24th_step_and_diffs_elsewhere():
    sim, _ = finished_sim(days=3)
    for frame in sim.frames:
        assert ("food" in frame) == (frame["step"] % 24 == 0)
        assert ("food_diff" in frame) == (frame["step"] % 24 != 0)


def test_a_30_day_rules_replay_is_under_3_mb():
    sim, _ = finished_sim(seed=7, days=30)
    size = len(dumps(build_replay(sim, "x")).encode())
    assert size < MAX_REPLAY_BYTES, f"{size / 1024:.0f} KB"


def test_a_crowded_month_stays_under_3_mb():
    """Worst case: every hour of a 30-day run with the cap's worth of creatures acting."""
    sim, _ = finished_sim(seed=7, days=2)
    template = sim.frames[10]
    agents = [template["agents"][0]] * 50
    frames = [dict(template, step=i, agents=agents) for i in range(721)]
    replay = build_replay(sim, "x")
    replay["frames"] = frames
    assert len(dumps(replay).encode()) < MAX_REPLAY_BYTES


def test_events_use_the_documented_sentences():
    sim, _ = finished_sim(seed=19, days=12)
    events = [e for frame in sim.frames for e in frame["events"]]
    assert events
    patterns = (" the wolf caught ", " the wolf missed ", " had ", " starved", " died of thirst")
    for event in events:
        assert any(p in event for p in patterns), event
    assert any(" the wolf caught " in e for e in events)


def test_a_wrong_format_is_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"format": "something/else"}))
    with pytest.raises(ValueError, match="replay@3"):
        read_replay(str(path))
    with pytest.raises(ValueError):
        check_format([])


def test_the_viewer_gets_the_replay_embedded_safely():
    sim, _ = finished_sim(days=1)
    replay = build_replay(sim, "x")
    replay["frames"][1]["events"].append("a </script><script>alert(1)</script> trick")
    html = '<html><body><script id="replay-data" type="application/json"></script><script>app()</script></body></html>'
    page = embed_in_viewer(html, replay)
    assert page.count("</script>") == 2  # only the page's own two script tags close
    start = page.index('type="application/json">') + len('type="application/json">')
    payload = json.loads(page[start:page.index("</script>", start)])
    assert payload["frames"][1]["events"][-1] == "a </script><script>alert(1)</script> trick"
    with pytest.raises(ValueError):
        embed_in_viewer("<html></html>", replay)


def test_run_one_writes_the_replay_and_returns_the_totals(tmp_path):
    spec = RunSpec(seed=7, brains={"rabbit": "rules", "deer": "rules", "wolf": "rules"}, days=2)
    result = run_one(spec, str(tmp_path / "out"))
    assert os.path.exists(result["paths"]["replay"]) and "requests" not in result["paths"]
    assert result["replay"]["meta"]["run_id"] == "run-rules-seed7"
    assert result["replay_bytes"] == os.path.getsize(result["paths"]["replay"])


def test_labels_and_run_ids():
    rules = {"rabbit": "rules", "deer": "rules", "wolf": "rules"}
    assert brain_label(rules) == "rules"
    mixed = {"rabbit": "rules", "deer": "rules", "wolf": "jev"}
    assert brain_label(mixed) == "wolf-jev_prey-rules"
    assert RunSpec(seed=7, brains=mixed, experiment="mixed").id == "mixed-wolf-jev_prey-rules-seed7"
    assert RunSpec(seed=7, brains={s: "jev" for s in rules}, experiment="survival").id == "survival-jev-seed7"
    assert RunSpec(seed=7, brains={s: "jev" for s in rules}, experiment="hesitation",
                   hesitate_below=0.3, hesitation_label="h-p10").id == "hesitation-jev-h-p10-seed7"
    assert RunSpec(seed=7, brains=rules, hesitate_below=0.4).id == "run-rules-h0.4-seed7"
    assert RunSpec(seed=7, brains={s: "system-one@http://x#m" for s in rules}).brain_label == "system-one"


def test_the_run_command_writes_a_replay(tmp_path, capsys):
    out = tmp_path / "r"
    spec = RunSpec(seed=7, brains={s: "rules" for s in SPECIES}, days=2)
    result = run_one(spec, str(out))  # the offline baseline is run through the benchmark's own path, not the CLI
    assert (out / "replay.json").exists() and result["paths"]["replay"].endswith("replay.json")


@pytest.mark.parametrize("command, flag", [("run", "--brain"), ("live", "--brain"), ("run", "--prey-brain"), ("live", "--wolf-brain")])
@pytest.mark.parametrize("name", ["rules", "random", "heuristic"])
def test_the_valley_does_not_run_without_a_model(command, flag, name, tmp_path, monkeypatch, capsys):
    """The hand-written brains were removed from the valley: only a model, or a server like one, can decide."""
    monkeypatch.undo()  # the tests' stand-in brains are switched off here: this is the real valley
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key-never-sent")  # so that the unknown brain is what fails, not a missing key
    assert cli.main([command, flag, name, "--out", str(tmp_path / "x")]) == 2
    message = capsys.readouterr().err
    assert f"unknown brain '{name}'" in message and "jev or system-one@URL#MODEL" in message
    assert not any((tmp_path / "x").glob("*.json")) if (tmp_path / "x").exists() else True


def test_there_is_no_offline_brain_in_the_valley(monkeypatch):
    monkeypatch.undo()
    import importlib.util
    from valley import brains
    assert brains.MODEL_BRAINS == ("jev",) and not hasattr(brains, "BASELINE_BRAINS")
    for module in ("valley.brains.rules", "valley.brains.random_brain"):
        assert importlib.util.find_spec(module) is None
    for name in ("rules", "random"):
        with pytest.raises(ValueError, match="runs only on a model"):
            brains.make_brain(name)


def test_the_run_command_reports_a_missing_key_without_a_traceback(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert cli.main(["run", "--brain", "jev", "--days", "1", "--out", str(tmp_path / "x"), "--quiet"]) == 2
    err = capsys.readouterr().err
    assert "TYPESAFE_API_KEY" in err and "Traceback" not in err


def test_the_run_command_stops_on_a_model_error_and_saves_nothing(tmp_path, capsys):
    out = tmp_path / "x"
    code = cli.main(["run", "--brain", "system-one@http://127.0.0.1:9#test-model", "--days", "1", "--out", str(out), "--quiet"])
    err = capsys.readouterr().err
    assert code == 2
    assert "the run stopped" in err and "Nothing was saved" in err and "--log-requests" in err
    assert not (out / "replay.json").exists() and not (out / "metrics.json").exists()


def test_the_view_command_embeds_a_replay(tmp_path, monkeypatch, capsys):
    sim, _ = finished_sim(days=1)
    replay_path = tmp_path / "replay.json"
    write_replay(str(replay_path), build_replay(sim, "x"))
    viewer = tmp_path / "index.html"
    viewer.write_text('<script id="replay-data" type="application/json"></script>')
    monkeypatch.setattr(cli, "VIEWER_PATH", viewer)
    out = tmp_path / "valley.html"
    assert cli.main(["view", str(replay_path), "-o", str(out)]) == 0
    assert '"format":"jev-valley/replay@3"' in out.read_text()


def test_creatures_carry_the_age_they_had_when_they_entered_the_valley():
    sim, _ = finished_sim(days=10)
    replay = build_replay(sim, "x")
    starters = [c for c in replay["creatures"].values() if c["born"] == 0]
    newborns = [c for c in replay["creatures"].values() if c["born"] > 0]
    assert starters and all(c["age0"] >= SPECIES[c["species"]].adult_age for c in starters)
    assert newborns and all(c["age0"] == 0 for c in newborns)


def test_run_and_live_use_a_model_by_default_so_they_need_a_key(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    parser = cli.build_parser()
    assert parser.parse_args(["run"]).brain == "jev" and parser.parse_args(["live"]).brain == "jev"
    assert cli.main(["run", "--days", "1", "--out", str(tmp_path / "x"), "--quiet"]) == 2
    assert "TYPESAFE_API_KEY" in capsys.readouterr().err
    assert not (tmp_path / "x").exists() or not (tmp_path / "x" / "replay.json").exists()
    assert cli.main(["live", "--port", "0", "--out", str(tmp_path / "y")]) == 2
    assert "TYPESAFE_API_KEY" in capsys.readouterr().err


def test_there_is_no_bundled_sample_run():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    assert not (root / "examples" / "sample-replay.json").exists()
    viewer = (root / "viewer" / "index.html").read_text()
    assert "load-sample" not in viewer and "sample-replay" not in viewer
    assert "sample-replay" not in (root / "README.md").read_text()


def test_retries_are_configurable_and_zero_means_stop_on_the_first_error():
    parser = cli.build_parser()
    assert cli._run_spec(parser.parse_args(["run"]), "run").options == {"max_retries": 2}
    assert cli._run_spec(parser.parse_args(["run", "--retries", "0"]), "run").options == {"max_retries": 0}
    assert cli._run_spec(parser.parse_args(["live", "--retries", "5"]), "live").options == {"max_retries": 5}
    assert parser.parse_args(["bench", "survival", "--retries", "0"]).retries == 0


def test_the_retry_setting_reaches_the_client(monkeypatch):
    from valley import bench
    monkeypatch.delenv("SYSTEM_ONE_API_KEY", raising=False)
    parser = cli.build_parser()
    spec = cli._run_spec(parser.parse_args(["run", "--brain", "system-one@http://127.0.0.1:9#m", "--retries", "0"]), "run")
    brains, instances = bench.build_brains(spec, None)
    assert instances[0].max_retries == 0


def test_the_viewer_explains_the_red_dashes_and_shows_real_model_usage():
    viewer = (Path(__file__).resolve().parent.parent / "viewer" / "index.html").read_text()
    assert 'id="hunt-toggle"' in viewer and "Wolf hunting its target" in viewer
    assert "model requests" in viewer and "offline" not in viewer.lower()


def test_the_viewer_accepts_the_format_the_server_writes_and_the_older_one():
    from pathlib import Path
    html = (Path(__file__).resolve().parent.parent / "viewer" / "index.html").read_text(encoding="utf-8")
    assert f'const FORMAT = "{FORMAT}";' in html
    assert '"jev-valley/replay@2"' in html and "FORMATS.includes(data.format)" in html


def test_the_viewer_redraws_at_once_after_a_resize_and_judges_speed_against_the_displays_own_rate():
    from pathlib import Path
    html = (Path(__file__).resolve().parent.parent / "viewer" / "index.html").read_text(encoding="utf-8")
    # a resize empties the canvas, so size() must draw again before the browser shows it (this was the white flash)
    assert "if (this.ready) this.renderer.render(this.scene, this.camera);" in html
    # the resolution only ever steps down, after two slow windows in a row, and relative to the display's frame time
    assert "watchFrameRate(frameMs)" in html and "this.slowWindows >= 2" in html and "this.refresh * 1.7" in html
    assert "avg < 13" not in html and "this.dpr + 0.1" not in html


def test_the_viewer_reads_the_answers_from_the_eleventh_item_of_a_row_and_shows_them():
    from pathlib import Path
    html = (Path(__file__).resolve().parent.parent / "viewer" / "index.html").read_text(encoding="utf-8")
    assert "path: 9, extras: 10" in html and "row[ROW.extras]" in html
    assert "Its other answers" in html and "extrasPanel(store, row[ROW.extras])" in html


def test_an_older_replay_without_the_rich_answers_can_still_be_read(tmp_path):
    sim, _ = finished_sim(days=1)
    replay = build_replay(sim, "old")
    replay["format"] = "jev-valley/replay@2"
    path = tmp_path / "old.json"
    path.write_text(dumps(replay))
    assert read_replay(str(path))["format"] == "jev-valley/replay@2"


def rows_of(sim):
    return [row for frame in sim.frames for row in frame["agents"] if row[3] is not None]


def test_rich_rows_carry_the_answers_as_an_eleventh_item_and_basic_rows_do_not():
    basic, _ = finished_sim(days=2)
    assert {len(row) for row in rows_of(basic)} == {10}
    assert build_replay(basic, "b")["meta"]["questions"] == "basic"
    b = make_brain("rules", 7)
    rich = Simulation(7, {s: b for s in SPECIES}, days=2, questions="rich")
    rich.run()
    rows = rows_of(rich)
    assert {len(row) for row in rows} == {11}
    assert all(isinstance(row[10], dict) and row[10] for row in rows)
    assert build_replay(rich, "r")["meta"]["questions"] == "rich"
    prey = next(row for row in rows if row[0].startswith("r"))
    assert set(prey[10]) == {"alert", "breed", "attack"}
    wolf = next(row for row in rows if row[0].startswith("w"))
    assert {"effort", "breed"} <= set(wolf[10]) and all(k in ("effort", "breed") or k.startswith("weak:") for k in wolf[10])


def test_a_newborn_has_no_answers_until_its_first_decision():
    b = make_brain("rules", 7)
    sim = Simulation(7, {s: b for s in SPECIES}, days=10, questions="rich")
    sim.run()
    newborn_rows = [row for frame in sim.frames for row in frame["agents"] if row[3] is None]
    assert newborn_rows and all(len(row) == 10 for row in newborn_rows)
