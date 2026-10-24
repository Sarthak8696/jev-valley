from valley import cli, tuning


def test_the_ten_benchmark_seeds():
    assert tuning.BENCH_SEEDS == (3, 7, 11, 19, 23, 42, 57, 64, 88, 101)


def test_tune_without_thresholds_does_nothing(capsys):
    assert cli.main(["tune"]) == 2
    assert "nothing to do" in capsys.readouterr().err


def test_the_offline_balance_check_is_gone():
    """The valley runs only on a model, so there is no offline way to check its balance."""
    assert not hasattr(tuning, "run_check") and not hasattr(tuning, "simulate_offline")
    assert not hasattr(tuning, "check_targets")
    with __import__("pytest").raises(SystemExit):
        cli.main(["tune", "--check"])
