from valley import cli, tuning
from valley.tuning import analyse, check_targets, rabbit_boom_bust, species_caps


def test_rabbit_boom_bust_needs_a_rise_and_a_30_percent_fall():
    assert rabbit_boom_bust([16, 20, 30, 20, 21]) is True      # 30 -> 20 is a 33% fall
    assert rabbit_boom_bust([16, 20, 30, 22, 25]) is False     # 30 -> 22 is a 27% fall
    assert rabbit_boom_bust([16, 12, 10, 8]) is False          # never rose above its start
    assert rabbit_boom_bust([16, 25, 0]) is True               # a crash to nothing counts
    assert rabbit_boom_bust([16, 17, 18, 19]) is False         # still climbing


def test_species_caps_follow_the_shares():
    assert species_caps(50) == {"rabbit": 30.0, "deer": 15.0, "wolf": 7.0}


def fake_run(seed, rabbits, deer, wolves, days=1):
    return {"brain": "rules", "seed": seed, "days": days,
            "pops": [[r, d, w] for r, d, w in zip(rabbits, deer, wolves)]}


def test_analyse_reports_final_counts_and_time_at_cap():
    steps = 25
    run = fake_run(1, [30] * steps, [5] * steps, [2] * steps, days=1)
    result = analyse(run)
    assert result["steps"] == 24 and result["all_alive"] is True
    assert result["final"] == {"rabbit": 30, "deer": 5, "wolf": 2}
    assert result["steps_at_cap"]["rabbit"] == 25 and result["steps_at_cap"]["deer"] == 0
    assert result["any_extinct"] is False


def test_a_run_that_ends_early_or_loses_a_species_is_not_all_alive():
    early = analyse(fake_run(1, [10] * 10, [5] * 10, [2] * 10, days=1))
    assert early["all_alive"] is False
    lost = analyse(fake_run(2, [10] * 25, [5] * 25, [2] * 24 + [0], days=1))
    assert lost["all_alive"] is False and lost["any_extinct"] is True


def analysed(n, **flags):
    base = dict(seed=0, steps=720, final={}, all_alive=False, boom_bust=False, any_extinct=False,
                steps_at_cap={"rabbit": 0, "deer": 0, "wolf": 0})
    base.update(flags)
    return [dict(base, seed=i) for i in range(n)]


def test_each_target_passes_and_fails_at_its_threshold():
    rules = analysed(10, all_alive=True, boom_bust=True)
    random_runs = analysed(10, any_extinct=True)
    assert all(t["passed"] for t in check_targets(rules, random_runs))

    few_alive = analysed(5, all_alive=True) + analysed(5, all_alive=False)
    targets = check_targets([dict(r, boom_bust=True) for r in few_alive], random_runs)
    assert targets[0]["passed"] is True
    targets = check_targets([dict(r, boom_bust=True) for r in analysed(4, all_alive=True) + analysed(6)], random_runs)
    assert targets[0]["passed"] is False

    assert check_targets(analysed(10, all_alive=True, boom_bust=False)[:], random_runs)[1]["passed"] is False
    two_booms = analysed(2, all_alive=True, boom_bust=True) + analysed(8, all_alive=True)
    assert check_targets(two_booms, random_runs)[1]["passed"] is False

    six_dead = analysed(6, any_extinct=True) + analysed(4)
    assert check_targets(rules, six_dead)[2]["passed"] is False
    assert check_targets(rules, analysed(7, any_extinct=True) + analysed(3))[2]["passed"] is True


def test_target_four_flags_a_species_sitting_at_its_cap_for_over_half_the_month():
    rules = analysed(10, all_alive=True, boom_bust=True)
    sitting = dict(rules[3], steps_at_cap={"rabbit": 361, "deer": 0, "wolf": 0})
    rules[3] = sitting
    target = check_targets(rules, analysed(10, any_extinct=True))[3]
    assert target["passed"] is False and "3" in target["text"]
    rules[3] = dict(sitting, steps_at_cap={"rabbit": 360, "deer": 0, "wolf": 0})
    assert check_targets(rules, analysed(10, any_extinct=True))[3]["passed"] is True


def test_the_ten_benchmark_seeds():
    assert tuning.BENCH_SEEDS == (3, 7, 11, 19, 23, 42, 57, 64, 88, 101)


def test_tune_without_check_does_nothing(capsys):
    assert cli.main(["tune"]) == 2
