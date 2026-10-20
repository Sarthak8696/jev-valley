import json
import os

import pytest

from valley import bench, cli, tuning
from valley.bench import (
    RunSpec, aggregate_group, estimate, plan_runs, render_markdown, resolve_dir, run_complete, run_dir,
    run_experiment, survival_twin,
)

SEEDS = [3, 7]


def quiet(*args, **kwargs):
    return None


def run(experiment, tmp_path, **kwargs):
    kwargs.setdefault("seeds", SEEDS)
    kwargs.setdefault("days", 2)
    return run_experiment(experiment, base_dir=str(tmp_path), out=quiet, **kwargs)


# -- planning ----------------------------------------------------------------------------------

def test_survival_plan_covers_every_brain_and_seed():
    specs = plan_runs("survival", SEEDS, 30)
    assert [s.id for s in specs] == [f"survival-{b}-seed{seed}" for b in ("jev", "laya", "rules", "random")
                                     for seed in SEEDS]
    assert all(set(s.brains.values()) == {s.brain_label} for s in specs)


def test_the_default_seeds_and_length():
    assert bench.BENCH_SEEDS == (3, 7, 11, 19, 23, 42, 57, 64, 88, 101)  # the full design, also used by tune --check
    assert bench.DEFAULT_SEEDS == (3, 7, 11, 19, 23)  # what bench runs unless told otherwise
    assert plan_runs("survival", bench.DEFAULT_SEEDS)[0].days == 30


def test_the_default_set_of_model_runs_is_about_twenty():
    thresholds = {"jev": {"p10": 0.5, "p25": 0.6}, "laya": {"p10": 0.4, "p25": 0.5}}
    survival = [s for s in plan_runs("survival", bench.DEFAULT_SEEDS) if s.uses_model]
    hesitation = [s for s in plan_runs("hesitation", bench.DEFAULT_SEEDS, thresholds=thresholds)
                  if s.uses_model and s.hesitation_label != "h-off"]  # `off` reuses the survival runs
    assert len(survival) == 10 and len(hesitation) == 10
    assert {s.brain_label for s in hesitation} == {"jev"}


def test_the_whole_design_is_still_one_flag_away():
    thresholds = {"jev": {"p10": 0.5, "p25": 0.6}, "laya": {"p10": 0.4, "p25": 0.5}}
    full = plan_runs("hesitation", bench.BENCH_SEEDS, thresholds=thresholds, brains=["jev", "laya"])
    assert len(full) == 2 * 3 * 10


def test_hesitation_plan_names_the_levels_and_uses_the_fixed_thresholds():
    thresholds = {"jev": {"p10": 0.61, "p25": 0.74}, "laya": {"p10": 0.4, "p25": 0.5}}
    specs = plan_runs("hesitation", [7], 30, thresholds=thresholds, brains=["jev", "laya"])
    assert [s.id for s in specs] == [
        "hesitation-jev-h-off-seed7", "hesitation-jev-h-p10-seed7", "hesitation-jev-h-p25-seed7",
        "hesitation-laya-h-off-seed7", "hesitation-laya-h-p10-seed7", "hesitation-laya-h-p25-seed7"]
    by_id = {s.id: s for s in specs}
    assert by_id["hesitation-jev-h-off-seed7"].hesitate_below is None
    assert by_id["hesitation-jev-h-p10-seed7"].hesitate_below == 0.61
    assert by_id["hesitation-laya-h-p25-seed7"].hesitate_below == 0.5


def test_hesitation_needs_thresholds_for_every_brain():
    only_jev = {"jev": {"p10": 0.5, "p25": 0.6}}
    with pytest.raises(KeyError):
        plan_runs("hesitation", [7], thresholds=only_jev, brains=["jev", "laya"])
    assert len(plan_runs("hesitation", [7], thresholds=only_jev)) == 3  # jev alone is the default
    with pytest.raises(FileNotFoundError, match="tune --thresholds"):
        bench.load_thresholds("/no/such/file.json")


def test_rivals_plan():
    specs = plan_runs("rivals", [7], 30)
    assert [s.id for s in specs] == ["rivals-wolf-jev_prey-laya-seed7", "rivals-wolf-laya_prey-jev-seed7"]
    assert specs[0].brains == {"rabbit": "laya", "deer": "laya", "wolf": "jev"}


def test_unknown_experiments_are_rejected():
    with pytest.raises(ValueError):
        plan_runs("nope", [1])


def test_benchmark_runs_never_use_the_cache():
    for experiment in ("survival", "rivals"):
        assert all(s.cache_dir is None for s in plan_runs(experiment, [7], 30, log_requests=True))
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["bench", "survival", "--cache"])


def test_the_estimate_is_starting_creatures_times_steps_times_one_and_a_half():
    specs = plan_runs("survival", [7], 30, brains=["jev"])
    est = estimate(specs)
    assert est["decisions"] == 26 * 720 * 1.5 == 28080
    assert est["requests"] == 1755 and est["batch"] == 16 and est["runs"] == 1
    assert estimate(plan_runs("survival", [7, 3], 30, brains=["jev"], batch=10))["requests"] == 5616


def test_a_hesitation_off_run_is_the_same_configuration_as_survival():
    specs = plan_runs("hesitation", [7], 30, thresholds={"jev": {"p10": 0.5, "p25": 0.6}}, brains=["jev"])
    off = specs[0]
    twin = survival_twin(off)
    assert twin.id == "survival-jev-seed7" and twin.brains == off.brains and twin.hesitate_below is None


# -- running and the results layout ----------------------------------------------------------

def test_a_survival_bench_with_rules_and_random_produces_the_full_layout(tmp_path):
    outcome = run("survival", tmp_path, brains=["rules", "random"])
    assert not outcome["aborted"] and len(outcome["ran"]) == 4
    root = tmp_path / "survival"
    for brain in ("rules", "random"):
        for seed in SEEDS:
            folder = root / f"survival-{brain}-seed{seed}"
            assert (folder / "replay.json").exists() and (folder / "metrics.json").exists()
            assert not (folder / "requests.jsonl").exists()  # model brains only
    assert (root / "summary.json").exists() and (root / "summary.md").exists()
    summary = json.loads((root / "summary.json").read_text())
    assert set(summary["groups"]) == {"rules", "random"} and summary["missing"] == []
    assert len(summary["runs"]) == 4 and summary["seeds"] == SEEDS
    md = (root / "summary.md").read_text()
    for heading in ("## Survival", "## Blunders", "## Cost and speed", "## All runs"):
        assert heading in md
    assert "survival-rules-seed3" in md


def test_the_three_charts_are_drawn_when_matplotlib_is_available(tmp_path):
    pytest.importorskip("matplotlib")
    run("survival", tmp_path, brains=["rules", "random"])
    for name in ("population.svg", "blunders.svg", "calibration.svg"):
        text = (tmp_path / "survival" / "charts" / name).read_text()
        assert text.lstrip().startswith("<?xml") and "<svg" in text


def test_finished_runs_are_skipped_unless_forced(tmp_path):
    run("survival", tmp_path, brains=["rules"])
    assert run("survival", tmp_path, brains=["rules"])["ran"] == []
    stamp = (tmp_path / "survival" / "survival-rules-seed3" / "metrics.json").stat().st_mtime_ns
    assert len(run("survival", tmp_path, brains=["rules"], force=True)["ran"]) == 2
    assert (tmp_path / "survival" / "survival-rules-seed3" / "metrics.json").stat().st_mtime_ns != stamp


def test_summary_only_does_not_run_anything(tmp_path):
    outcome = run("survival", tmp_path, brains=["rules"], summary_only=True)
    assert outcome["ran"] == []
    assert "No runs have finished yet." in (tmp_path / "survival" / "summary.md").read_text()
    assert not (tmp_path / "survival" / "survival-rules-seed3").exists()


def test_run_complete_checks_seed_and_threshold(tmp_path):
    run("survival", tmp_path, brains=["rules"], seeds=[3])
    spec = plan_runs("survival", [3], 2, brains=["rules"])[0]
    assert run_complete(run_dir(str(tmp_path), spec), spec)
    other = plan_runs("survival", [7], 2, brains=["rules"])[0]
    assert not run_complete(run_dir(str(tmp_path), spec), other)
    frozen = RunSpec(3, spec.brains, "survival", 2, hesitate_below=0.3)
    assert not run_complete(run_dir(str(tmp_path), spec), frozen)


def test_model_runs_need_confirmation_and_nothing_runs_without_it(tmp_path, monkeypatch):
    for name in ("LAYA_BASE_URL", "LAYA_MODEL", "LAYA_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(bench, "confirm", lambda question: False)
    messages = []
    outcome = run_experiment("survival", base_dir=str(tmp_path), seeds=[3], days=2, brains=["laya"],
                             out=messages.append)
    assert outcome["aborted"] is True and outcome["ran"] == []
    assert any("call a model" in m and "28" not in m or "decisions" in m for m in messages)
    assert not (tmp_path / "survival" / "survival-laya-seed3").exists()


def test_a_missing_key_stops_the_run_before_any_prompt(tmp_path, monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="TYPESAFE_API_KEY"):
        run_experiment("survival", base_dir=str(tmp_path), seeds=[3], days=2, brains=["jev"], out=quiet, yes=True)


def test_offline_brains_never_ask_for_confirmation(tmp_path, monkeypatch):
    monkeypatch.setattr(bench, "confirm", lambda q: pytest.fail("asked for confirmation"))
    assert len(run("survival", tmp_path, brains=["rules"])["ran"]) == 2


def test_hesitation_reuses_survival_for_the_off_condition(tmp_path):
    run("survival", tmp_path, brains=["rules"], seeds=[3])
    (tmp_path / "hesitation").mkdir()
    (tmp_path / "hesitation" / "thresholds.json").write_text(
        json.dumps({"brains": {"rules": {"p10": 0.25, "p25": 0.45}}}))
    outcome = run("hesitation", tmp_path, brains=["rules"], seeds=[3])
    assert sorted(outcome["ran"]) == ["hesitation-rules-h-p10-seed3", "hesitation-rules-h-p25-seed3"]
    summary = json.loads((tmp_path / "hesitation" / "summary.json").read_text())
    assert set(summary["groups"]) == {"rules-h-off", "rules-h-p10", "rules-h-p25"}
    off = next(r for r in summary["runs"] if r["group"] == "rules-h-off")
    assert off["reused_from"] == "survival-rules-seed3"
    assert summary["groups"]["rules-h-p10"]["hesitation_threshold"] == 0.25
    assert summary["groups"]["rules-h-p10"]["hesitation_rate"] > 0
    md = (tmp_path / "hesitation" / "summary.md").read_text()
    assert "Hesitation threshold" in md and "(from survival-rules-seed3)" in md


def test_hesitation_without_reuse_runs_its_own_off_condition(tmp_path):
    (tmp_path / "hesitation").mkdir()
    (tmp_path / "hesitation" / "thresholds.json").write_text(
        json.dumps({"brains": {"rules": {"p10": 0.25, "p25": 0.45}}}))
    outcome = run("hesitation", tmp_path, brains=["rules"], seeds=[3])
    assert "hesitation-rules-h-off-seed3" in outcome["ran"] and len(outcome["ran"]) == 3


def test_resolve_dir_falls_back_when_survival_is_missing(tmp_path):
    spec = plan_runs("hesitation", [3], 2, thresholds={"rules": {"p10": 0.2, "p25": 0.3}}, brains=["rules"])[0]
    directory, reused = resolve_dir(str(tmp_path), spec)
    assert reused is None and directory.endswith("hesitation-rules-h-off-seed3")


# -- summaries ---------------------------------------------------------------------------------

def fake_metrics(valid=True, hours=720, alive=True, rate=0.1, seed=1):
    return {
        "run_id": f"x-seed{seed}", "seed": seed, "brains": {}, "hesitate_below": None, "valid": valid,
        "fallbacks": {"decisions": 100, "fallbacks": 0 if valid else 50, "rate": 0.0 if valid else 0.5},
        "survival": {"hours_survived": hours, "first_extinction": None, "all_species_alive": alive,
                     "final_population": {"rabbit": 10, "deer": 4, "wolf": 2},
                     "mean_population": {"rabbit": 12.0, "deer": 5.0, "wolf": 2.5}, "births": {}, "deaths_by_cause": {}},
        "hesitation": {"threshold": None, "decisions": 100, "hesitated": 0, "rate": None},
        "blunders": {"jev": {"opportunities": {"ignored_danger": 10}, "blunders": {"ignored_danger": int(rate * 10)},
                             "overall_blunder_rate": rate, "blunders_per_1000_decisions": 5.0,
                             "scored_decisions": 100, "fallbacks": 0}},
        "calibration": {"jev": [{"bin": b, "decisions_with_opportunity": 10, "blunder_rate": rate}
                                for b in ("0.0-0.2", "0.2-0.4", "0.4-0.6", "0.6-0.8", "0.8-1.0")]},
        "cost": {"jev": {"decisions": 100, "requests": 10, "fallbacks": 0 if valid else 50, "fallback_rate": 0.0,
                         "retries": 1, "input_tokens": 1000, "output_tokens": 100,
                         "input_tokens_per_1000_decisions": 10000.0, "output_tokens_per_1000_decisions": 1000.0,
                         "latency_ms_p50": 200.0, "latency_ms_p95": 400.0,
                         "seconds_per_valley_hour_p50": 0.5, "seconds_per_valley_hour_p95": 0.9}},
    }


def test_invalid_runs_are_left_out_of_medians_but_still_counted_and_listed():
    runs = [{"metrics": fake_metrics(hours=600, rate=0.1)}, {"metrics": fake_metrics(hours=720, rate=0.3)},
            {"metrics": fake_metrics(valid=False, hours=10, alive=False, rate=0.9)}]
    group = aggregate_group(runs)
    assert group["runs"] == 3 and group["valid_runs"] == 2
    assert group["median_hours_survived"] == 660
    assert group["runs_all_species_alive"] == 2
    assert group["mean_blunder_rate"] == pytest.approx(0.2)
    assert group["blunder_rates"] == [0.1, 0.3]
    assert group["cost"]["jev"]["decisions"] == 200
    assert group["calibration"]["jev"][0]["decisions_with_opportunity"] == 20
    summary = {"experiment": "survival", "seeds": [1], "days": 30, "groups": {"jev": group}, "missing": [],
               "runs": [{"run_id": f"survival-jev-seed{i}", "group": "jev", "reused_from": None, "metrics": r["metrics"]}
                        for i, r in enumerate(runs)]}
    md = render_markdown(summary)
    assert "| jev | 2/3 |" in md
    assert "survival-jev-seed2 | **no**" in md


def test_the_markdown_has_no_hand_typed_numbers_only_table_cells():
    group = aggregate_group([{"metrics": fake_metrics()}])
    summary = {"experiment": "survival", "seeds": [1], "days": 30, "groups": {"jev": group}, "missing": ["x"],
               "runs": []}
    md = render_markdown(summary)
    assert "Not yet run: x" in md and "## Calibration" in md


# -- thresholds -------------------------------------------------------------------------------

def test_nearest_rank_percentiles():
    values = list(range(1, 101))
    assert tuning.percentile_nearest_rank(values, 10) == 10
    assert tuning.percentile_nearest_rank(values, 25) == 25
    assert tuning.percentile_nearest_rank([0.9, 0.2, 0.5], 10) == 0.2
    assert tuning.percentile_nearest_rank([0.7], 25) == 0.7
    with pytest.raises(ValueError):
        tuning.percentile_nearest_rank([], 10)


def write_requests(path, brain, confidences):
    answers = {f"r{i}": {"type": "choice", "choice": "eat", "probabilities": {"eat": 1.0}, "confidence": c}
               for i, c in enumerate(confidences)}
    answers["bad"] = {"type": "choice", "choice": "eat"}  # no confidence: ignored
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"brain": brain, "step": 1, "request": {}, "response": {"answers": answers},
                                 "error": None}) + "\n")
        handle.write(json.dumps({"brain": brain, "step": 2, "request": {}, "response": None, "error": "HTTP 500"}) + "\n")


def test_thresholds_come_from_each_brains_own_confidences(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    write_requests(tmp_path / "a" / "requests.jsonl", "jev", [i / 100 for i in range(50, 100)])
    write_requests(tmp_path / "a" / "requests.jsonl", "laya", [i / 100 for i in range(1, 51)])
    write_requests(tmp_path / "b" / "requests.jsonl", "jev", [i / 100 for i in range(100, 150)])
    result = tuning.thresholds_from_runs([str(tmp_path / "a"), str(tmp_path / "b")])
    jev, laya = result["brains"]["jev"], result["brains"]["laya"]
    assert jev["decisions"] == 100 and laya["decisions"] == 50
    assert jev["p10"] == pytest.approx(0.59) and jev["p25"] == pytest.approx(0.74)
    assert laya["p10"] == pytest.approx(0.05) and laya["p25"] == pytest.approx(0.13)
    assert result["percentiles"] == [10, 25] and result["source_runs"] == ["a", "b"]
    out = tmp_path / "t" / "thresholds.json"
    tuning.write_thresholds(str(out), result)
    assert bench.load_thresholds(str(out))["jev"]["p10"] == pytest.approx(0.59)


def test_thresholds_fall_back_to_the_replay_when_there_is_no_request_log(tmp_path):
    run("survival", tmp_path, brains=["rules"], seeds=[3], days=2)
    folder = tmp_path / "survival" / "survival-rules-seed3"
    result = tuning.thresholds_from_runs([str(folder)])
    assert result["brains"]["rules"]["p10"] <= result["brains"]["rules"]["p25"] <= 1.0
    with pytest.raises(FileNotFoundError):
        tuning.thresholds_from_runs([str(tmp_path / "nowhere")])


def test_the_tune_command_writes_thresholds(tmp_path, capsys):
    run("survival", tmp_path, brains=["rules"], seeds=[3], days=2)
    out = tmp_path / "th.json"
    folder = str(tmp_path / "survival" / "survival-rules-seed3")
    assert cli.main(["tune", "--thresholds", folder, "-o", str(out)]) == 0
    assert json.loads(out.read_text())["brains"]["rules"]["decisions"] > 0
    assert "rules: p10" in capsys.readouterr().out
    assert cli.main(["tune", "--thresholds", str(tmp_path / "nowhere"), "-o", str(out)]) == 2


# -- the command ---------------------------------------------------------------------------------

def test_the_bench_command(tmp_path, capsys):
    code = cli.main(["bench", "survival", "--brains", "rules", "--seeds", "3", "--days", "2", "--out", str(tmp_path)])
    assert code == 0
    assert (tmp_path / "survival" / "summary.md").exists()
    assert "survival-rules-seed3" in capsys.readouterr().out


def test_the_bench_command_reports_missing_thresholds(tmp_path, capsys):
    code = cli.main(["bench", "hesitation", "--brains", "rules", "--seeds", "3", "--days", "2", "--out", str(tmp_path)])
    assert code == 2
    assert "tune --thresholds" in capsys.readouterr().err


def test_the_bench_command_exits_non_zero_when_not_confirmed(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(bench, "confirm", lambda q: False)
    monkeypatch.delenv("LAYA_BASE_URL", raising=False)
    code = cli.main(["bench", "survival", "--brains", "laya", "--seeds", "3", "--days", "2", "--out", str(tmp_path)])
    assert code == 1
    assert "not confirmed" in capsys.readouterr().out
