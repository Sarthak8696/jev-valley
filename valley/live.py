"""Live mode: runs the valley and streams each finished hour to the viewer as it is decided.

The loop asks the brain for every animal's decision, carries out the hour, sends the
frame, and never sends frames faster than one per `pace` seconds. If decisions take
longer than that, the next frame goes out as soon as it is ready and the valley's
clock slows down: decisions are never skipped or guessed. The server binds to
127.0.0.1 only. When the month ends or every viewer has left, the run is saved as a
normal replay with its `requests.jsonl`.
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from valley import bench
from valley.replay import FORMAT, creature_record, replay_meta

VIEWER_PATH = Path(__file__).resolve().parent.parent / "viewer" / "index.html"
LIVE_TAG = '<meta name="valley-live" content="">'
STREAM_PATH = "/stream"
KEEPALIVE_SECONDS = 15
LOCAL_HOST = "127.0.0.1"


def viewer_page(path: Path = VIEWER_PATH) -> str:
    """The viewer with its live-mode tag filled in, so it connects to this server's stream."""
    html = path.read_text(encoding="utf-8")
    if LIVE_TAG not in html:
        raise ValueError("the viewer has no empty valley-live meta tag to fill")
    return html.replace(LIVE_TAG, f'<meta name="valley-live" content="{STREAM_PATH}">', 1)


class LiveServer:
    def __init__(self, spec: bench.RunSpec, out_dir: str | None, port: int = 8765, pace: float = 1.0,
                 disconnect_grace: float = 5.0, wait_for_viewer: bool = True, viewer_path: Path = VIEWER_PATH,
                 out=print):
        self.spec = spec
        self.out_dir = out_dir
        self.pace = pace
        self.disconnect_grace = disconnect_grace
        self.wait_for_viewer = wait_for_viewer
        self.out = out
        self._page = viewer_page(viewer_path)
        self.sim, self.instances = bench.prepare_run(spec, out_dir)

        self._cond = threading.Condition()
        self._messages: list[tuple[str, str]] = []
        self._clients = 0
        self._had_client = False
        self._idle_since: float | None = None
        self._viewer_seen = threading.Event()
        self._stop = threading.Event()
        self.finished = threading.Event()
        self.result: dict | None = None
        self.error: BaseException | None = None
        self._note_counts = {c.id: len(c.notes) for c in self.sim.creatures.values()}

        self._publish("meta", {
            "format": FORMAT, "meta": replay_meta(self.sim, spec.id),
            "creatures": {c.id: creature_record(c) for c in self.sim.creatures.values()},
            "frames": [self.sim.frames[0]],
        })
        self.httpd = ThreadingHTTPServer((LOCAL_HOST, port), self._handler())
        self.port = self.httpd.server_address[1]
        self._threads: list[threading.Thread] = []

    @property
    def url(self) -> str:
        return f"http://{LOCAL_HOST}:{self.port}/"

    # -- messages ---------------------------------------------------------

    def _publish(self, event: str, payload: dict) -> None:
        with self._cond:
            self._messages.append((event, json.dumps(payload, separators=(",", ":"))))
            self._cond.notify_all()

    def _extras(self, frame: dict, seconds: float) -> dict:
        step = frame["step"]
        created, fates, notes = {}, {}, {}
        for c in self.sim.creatures.values():
            if c.born == step and c.id not in self._note_counts:
                created[c.id] = creature_record(c)
                self._note_counts[c.id] = len(c.notes)
            if c.died == step:
                fates[c.id] = {"died": c.died, "cause": c.cause}
            seen = self._note_counts.get(c.id, 0)
            if len(c.notes) > seen:
                notes[c.id] = c.notes[seen:]
                self._note_counts[c.id] = len(c.notes)
        return {
            "pace": {"seconds_this_hour": round(seconds, 3),
                     "hours_per_second": round(1.0 / max(self.pace, seconds, 1e-6), 2)},
            "new_creatures": created, "notes": notes, "fates": fates,
        }

    # -- the simulation thread --------------------------------------------

    def _should_stop(self) -> bool:
        if self._stop.is_set():
            return True
        with self._cond:
            idle = self._idle_since
            return (self._had_client and self._clients == 0 and idle is not None
                    and time.monotonic() - idle > self.disconnect_grace)

    def _run_simulation(self) -> None:
        try:
            if self.wait_for_viewer:
                while not self._viewer_seen.wait(0.2):
                    if self._stop.is_set():
                        return
            last_sent = None
            while (self.sim.step_no < self.sim.steps and any(c.alive for c in self.sim.living)
                   and not self._should_stop()):
                started = time.monotonic()
                frame = self.sim.step()
                ready = time.monotonic()
                if last_sent is not None:
                    self._stop.wait(max(0.0, last_sent + self.pace - ready))
                if self._should_stop():
                    break
                payload = dict(frame)
                payload.update(self._extras(frame, ready - started))
                self._publish("frame", payload)
                last_sent = time.monotonic()
        except BaseException as exc:  # reported to the caller; the stream still ends cleanly
            self.error = exc
        finally:
            self._finish()

    def _finish(self) -> None:
        try:
            self.result = bench.finish_run(self.sim, self.instances, self.spec, self.out_dir)
            saved = self.result["paths"].get("replay")
        except BaseException as exc:
            self.error = self.error or exc
            saved = None
        self._publish("end", {"saved": saved, "hours": self.sim.step_no})
        self.finished.set()

    # -- the HTTP side ----------------------------------------------------

    def _handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                return None

            def do_GET(self):
                path = self.path.split("?")[0]
                if path in ("/", "/index.html"):
                    body = server._page.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(body)
                elif path == STREAM_PATH:
                    server._stream(self)
                elif path == "/favicon.ico":
                    self.send_response(204)
                    self.end_headers()
                else:
                    self.send_error(404)

        return Handler

    def _stream(self, handler: BaseHTTPRequestHandler) -> None:
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.send_header("Cache-Control", "no-cache")
        handler.send_header("X-Accel-Buffering", "no")
        handler.end_headers()
        with self._cond:
            self._clients += 1
            self._had_client = True
            self._idle_since = None
        self._viewer_seen.set()
        index = 0
        try:
            while True:
                keepalive = False
                with self._cond:
                    while index >= len(self._messages) and not self.finished.is_set():
                        if not self._cond.wait(KEEPALIVE_SECONDS):
                            keepalive = True
                            break
                    batch = self._messages[index:]
                if keepalive and not batch:
                    handler.wfile.write(b": keepalive\n\n")
                    handler.wfile.flush()
                    continue
                for event, text in batch:
                    handler.wfile.write(f"event: {event}\ndata: {text}\n\n".encode("utf-8"))
                handler.wfile.flush()
                index += len(batch)
                if self.finished.is_set() and index >= len(self._messages):
                    break
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        finally:
            with self._cond:
                self._clients -= 1
                if self._clients == 0:
                    self._idle_since = time.monotonic()

    # -- lifecycle --------------------------------------------------------

    def start(self) -> None:
        """Start serving and, once a viewer connects, simulating. Does not block."""
        for target in (lambda: self.httpd.serve_forever(poll_interval=0.05), self._run_simulation):
            thread = threading.Thread(target=target, daemon=True)
            thread.start()
            self._threads.append(thread)

    def stop(self) -> None:
        self._stop.set()

    def close(self) -> None:
        """Stop the simulation, wait for the run to be saved, and shut the server down."""
        self._stop.set()
        self._viewer_seen.set()
        self.finished.wait(60)
        time.sleep(0.05)  # let open streams flush their last events
        self.httpd.shutdown()
        self.httpd.server_close()

    def run(self) -> None:
        """Serve until the run ends. Ctrl-C stops early and still saves what has been decided."""
        self.start()
        self.out(f"Jev Valley live at {self.url}")
        if self.wait_for_viewer:
            self.out("Waiting for a viewer to connect before the valley starts.")
        try:
            while not self.finished.wait(0.5):
                pass
        except KeyboardInterrupt:
            self.out("Stopping; saving what has been decided so far.")
            self._stop.set()
            self.finished.wait(60)
        finally:
            self.close()
        if self.error:
            raise self.error
        if self.result and self.result["paths"].get("replay"):
            self.out(f"saved {self.result['paths']['replay']}")
