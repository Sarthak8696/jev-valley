"""Runs the viewer's own motion code under Node against a real replay and checks that nobody teleports.

The viewer is one HTML file, so the pure part (helpers, replay store, tracks and scene state) is cut out between two
markers and run with a stubbed `window`. Skipped when Node is not installed.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.offline import make_offline_brain
from valley.replay import build_replay, write_replay
from valley.simulation import Simulation
from valley.species import SPECIES

VIEWER = Path(__file__).resolve().parent.parent / "viewer" / "index.html"
START = "/* ---- begin pure code"
END = "/* ---- end pure code */"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node is not installed")

HARNESS = """
const window = { matchMedia: () => ({ matches: false }) };
%(code)s
const fs = require("fs");
const store = new Store(JSON.parse(fs.readFileSync(process.argv[2], "utf8")));
const tracks = new Tracks(store);

function sweep(fps, speed, to) {
  let prev = null, worst = 0, jumps = 0, samples = 0, worstFast = 0;
  const dT = speed / fps;
  for (let T = 0; T <= to; T += dT) {
    const scene = sceneAt(store, tracks, T);
    const now = new Map(scene.animals.map(a => [a.id, a]));
    if (prev) for (const [id, a] of now) {
      const p = prev.get(id);
      if (!p) continue;
      const d = Math.hypot(a.x - p.x, a.y - p.y);
      samples++;
      if (d > worst) worst = d;
      if (d >= 0.5) jumps++;
      // a step can never be longer than the animal's own speed allows, so a larger one would be a jump in the data
      worstFast = Math.max(worstFast, d / (dT * Math.max(a.speed, p.speed, 0.5)));
    }
    prev = now;
  }
  return { worst, jumps, samples, worstFast };
}

const last = store.lastStep;
let outside = 0, fast = 0;
for (let T = 0; T <= last; T += 0.25) for (const a of sceneAt(store, tracks, T).animals) {
  if (a.x < -0.6 || a.y < -0.6 || a.x > store.meta.width + 0.6 || a.y > store.meta.height + 0.6) outside++;
  fast = Math.max(fast, a.speed);
}
console.log(JSON.stringify({
  normal: sweep(60, 1, last),            // one hour per second on a 60 fps screen
  scrub: sweep(60, 6, last),             // dragging the timeline: far quicker than playback; an animal still never steps further than its own speed allows
  outside, fastest: fast, animals: tracks.byId.size,
  liveLimit: [tracks.maxTime(false), tracks.maxTime(true), last],
}));
"""


@pytest.fixture(scope="module")
def measured(tmp_path_factory):
    folder = tmp_path_factory.mktemp("motion")
    brain = make_offline_brain("rules", 57)  # a stand-in for a model: the valley itself cannot run without one
    sim = Simulation(57, {s: brain for s in SPECIES}, days=5, questions="rich")
    sim.run()
    replay_path = folder / "replay.json"
    write_replay(str(replay_path), build_replay(sim, "motion"))
    result = {"paths": {"replay": str(replay_path)}}
    html = VIEWER.read_text(encoding="utf-8")
    code = html[html.index(START):html.index(END) + len(END)]
    script = folder / "motion.js"
    script.write_text(HARNESS % {"code": code}, encoding="utf-8")
    out = subprocess.run(["node", str(script), result["paths"]["replay"]], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_at_normal_speed_nobody_jumps_between_two_frames(measured):
    normal = measured["normal"]
    assert normal["samples"] > 10_000
    assert normal["jumps"] == 0, f"{normal['jumps']} frames moved an animal half a tile or more"
    assert normal["worst"] < 0.2, f"largest move in one frame was {normal['worst']:.2f} tiles"


def test_a_frame_never_moves_an_animal_further_than_its_own_speed_allows(measured):
    """The curve is continuous: the step between two frames matches the speed read from the same curve."""
    assert measured["normal"]["worstFast"] < 1.6
    assert measured["scrub"]["worstFast"] < 1.6


def test_animals_stay_on_the_map_and_none_is_unreasonably_fast(measured):
    assert measured["outside"] == 0
    assert measured["fastest"] < 8, f"fastest animal moved {measured['fastest']:.1f} tiles per hour"


def test_a_live_run_shows_one_hour_behind_until_it_has_ended(measured):
    live_limit, final_limit, last = measured["liveLimit"]
    assert final_limit == last and live_limit == last - 1


def test_the_viewer_has_the_markers_the_test_relies_on():
    html = VIEWER.read_text(encoding="utf-8")
    assert START in html and END in html and html.index(START) < html.index(END)
