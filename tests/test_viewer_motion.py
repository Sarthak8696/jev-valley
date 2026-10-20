"""Runs the viewer's own motion code under Node against a real replay and checks that nobody teleports.

The viewer is one HTML file, so the pure part (helpers, replay store, scene state) is cut out between two
section markers and run with a stubbed `window`. Skipped when Node is not installed.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from valley.bench import RunSpec, run_one

VIEWER = Path(__file__).resolve().parent.parent / "viewer" / "index.html"
START = "/* ------------------------------------------------------------------ helpers */"
END = "/* ------------------------------------------------------------------ lighting (visual only) */"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node is not installed")

HARNESS = """
const window = { matchMedia: () => ({ matches: false }) };
%(code)s
const fs = require("fs");
const store = new Store(JSON.parse(fs.readFileSync(process.argv[2], "utf8")));

function sweep(stepsPerHour, glide, from, to) {
  let prev = null, worst = 0, jumps = 0, samples = 0;
  for (let i = from * stepsPerHour; i <= to * stepsPerHour; i++) {
    const scene = computeScene(store, i / stepsPerHour, glide);
    const now = new Map(scene.animals.map(a => [a.id, [a.x, a.y]]));
    if (prev) for (const [id, [x, y]] of now) {
      const p = prev.get(id);
      if (!p) continue;
      const d = Math.hypot(x - p[0], y - p[1]);
      samples++;
      if (d > worst) worst = d;
      if (d >= 0.5) jumps++;
    }
    prev = now;
  }
  return { worst, jumps, samples };
}

const last = store.lastStep;
console.log(JSON.stringify({
  normal: sweep(60, false, 0, last),          // 1x on a 60 fps screen
  fast: sweep(15, true, 0, last),             // 4x on a 60 fps screen
  easing: [easeInOut(-3), easeInOut(0), easeInOut(0.5), easeInOut(1), easeInOut(4)],
}));
"""


@pytest.fixture(scope="module")
def measured(tmp_path_factory):
    folder = tmp_path_factory.mktemp("motion")
    spec = RunSpec(seed=57, brains={k: "rules" for k in ("rabbit", "deer", "wolf")}, days=5)
    result = run_one(spec, str(folder / "run"))
    html = VIEWER.read_text(encoding="utf-8")
    code = html[html.index(START):html.index(END)]
    script = folder / "motion.js"
    script.write_text(HARNESS % {"code": code}, encoding="utf-8")
    out = subprocess.run(["node", str(script), result["paths"]["replay"]], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_easing_stays_between_zero_and_one_whatever_it_is_given(measured):
    """Before a move starts it is 0 and after it ends it is 1. This was the cause of animals teleporting."""
    before, start, middle, end, after = measured["easing"]
    assert (before, start, middle, end, after) == (0, 0, 0.5, 1, 1)


def test_at_normal_speed_nobody_jumps_between_two_frames(measured):
    normal = measured["normal"]
    assert normal["samples"] > 10_000
    assert normal["jumps"] == 0, f"{normal['jumps']} frames moved an animal half a tile or more"
    assert normal["worst"] < 0.35, f"largest move in one frame was {normal['worst']:.2f} tiles"


def test_at_4x_animals_glide_instead_of_jumping(measured):
    fast = measured["fast"]
    assert fast["jumps"] == 0, f"{fast['jumps']} frames moved an animal half a tile or more"
    assert fast["worst"] < 0.5, f"largest move in one frame was {fast['worst']:.2f} tiles"


def test_the_viewer_has_the_markers_the_test_relies_on():
    html = VIEWER.read_text(encoding="utf-8")
    assert START in html and END in html and html.index(START) < html.index(END)
