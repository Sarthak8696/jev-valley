import re

import pytest

pytest.importorskip("matplotlib")

from valley import charts  # noqa: E402

RUNS = {"jev": 10, "rules": 10, "random": 9}


def series(scale):
    return {key: [scale * (1 + (i % 7)) for i in range(721)] for key in ("rabbit", "deer", "wolf")}


def read(path):
    return path.read_text()


def test_population_chart_draws_every_brain_in_its_own_color(tmp_path):
    path = tmp_path / "population.svg"
    charts.population_chart(str(path), {"jev": series(3), "rules": series(2), "random": series(1)}, RUNS)
    text = read(path)
    assert "<svg" in text and "Median population over the month" in text
    for color in ("#2a78d6", "#1baf7a", "#898781"):
        assert color in text
    for label in ("Rabbits", "Deer", "Wolves", "Jev", "Rules", "Random"):
        assert label in text
    assert "Runs per line: Jev: 10, Rules: 10, Random: 9" in text


def test_charts_are_reproducible_byte_for_byte(tmp_path):
    a, b = tmp_path / "a.svg", tmp_path / "b.svg"
    for path in (a, b):
        charts.population_chart(str(path), {"jev": series(3)}, {"jev": 10})
    assert a.read_bytes() == b.read_bytes()
    assert "Date" not in re.findall(r"<dc:date>.*?</dc:date>", read(a)) and "<dc:date>" not in read(a)


def test_charts_use_the_light_chart_surface(tmp_path):
    path = tmp_path / "blunders.svg"
    charts.blunders_chart(str(path), {"rules": [0.05, 0.07], "random": [0.4, 0.45]})
    assert "#fcfcfb" in read(path)


def test_blunders_chart_shows_the_mean_of_each_brain(tmp_path):
    path = tmp_path / "blunders.svg"
    charts.blunders_chart(str(path), {"rules": [0.05, 0.07], "random": [0.4, 0.5]})
    text = read(path)
    assert "6.0%" in text and "45.0%" in text
    assert "Random" in text and "Rules" in text


def test_blunders_chart_with_no_data_says_so(tmp_path):
    path = tmp_path / "empty.svg"
    charts.blunders_chart(str(path), {})
    assert "no valid runs to draw" in read(path)
    charts.blunders_chart(str(path), {"jev": []})
    assert "no valid runs to draw" in read(path)


def test_calibration_chart_has_one_line_per_model_brain(tmp_path):
    bins = [{"bin": b, "decisions_with_opportunity": 10, "blunder_rate": r}
            for b, r in zip(("0.0-0.2", "0.2-0.4", "0.4-0.6", "0.6-0.8", "0.8-1.0"), (0.5, 0.3, None, 0.1, 0.05))]
    path = tmp_path / "calibration.svg"
    charts.calibration_chart(str(path), {"jev": bins, "system-one": bins})
    text = read(path)
    assert "Blunders by confidence" in text and "0.8-1.0" in text and "#2a78d6" in text and "#6250d6" in text
    charts.calibration_chart(str(path), {})
    assert "no model decisions to draw" in read(path)


def test_hesitation_groups_share_a_brain_color_and_differ_by_line_style():
    style = charts.Style(["jev-h-off", "jev-h-p10", "jev-h-p25", "rules-h-off"])
    assert style.colors["jev-h-off"] == style.colors["jev-h-p10"] == style.colors["jev-h-p25"] == "#2a78d6"
    assert style.colors["rules-h-off"] == "#1baf7a"
    assert len({style.line_style(g) for g in ("jev-h-off", "jev-h-p10", "jev-h-p25")}) == 3
    assert charts.brain_of("wolf-jev_prey-rules") == "wolf-jev_prey-rules"
    assert charts.condition_of("jev-h-p25") == "p25" and charts.condition_of("jev") is None


def test_mixed_brain_groups_get_extra_colors_that_stay_stable():
    style = charts.Style(["wolf-jev_prey-rules", "wolf-rules_prey-jev", "jev"])
    assert style.colors["jev"] == "#2a78d6"
    assert style.colors["wolf-jev_prey-rules"] != style.colors["wolf-rules_prey-jev"]
    assert style.colors["wolf-jev_prey-rules"] not in ("#2a78d6", "#1baf7a", "#898781")
    assert len(set(style.markers.values())) == 3


def test_pretty_names():
    assert charts._pretty("jev") == "Jev"
    assert charts._pretty("jev-h-p10") == "Jev, hesitates below 10th percentile"
    assert charts._pretty("jev-h-off") == "Jev, no hesitation"
