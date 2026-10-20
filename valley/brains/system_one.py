"""The System One client, used for Jev and for any other server that speaks the same API.

Every creature gets one `Choice` question. Several creatures are batched into one
request, and requests run in parallel. If a call fails, or an answer is missing or
invalid, that creature rests and the decision is marked as a fallback and counted.
The API key travels only in the Authorization header and is never logged.
"""

import hashlib
import json
import os
import socket
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from valley.brains.base import Brain, Decision, DecisionRequest

INSTRUCTIONS = (
    "You are deciding the next action of one wild animal in a valley for the coming hour. "
    "Weigh its hunger, thirst, nearby dangers, chances to breed and its personality, "
    "then pick the single action it takes now."
)
BATCH_SENTENCE = "Decide only for the creature with id '{id}', using creatures['{id}']."

ENDPOINT = "/v1/systemone"
REQUEST_ID_HEADER = "x-typesafe-request-id"
SINGLE_QUESTION_ID = "action"

DEFAULT_BATCH = 16
DEFAULT_WORKERS = 4
DEFAULT_TIMEOUT = 30
MAX_RETRIES = 2
BACKOFF_SECONDS = 0.5
MAX_RETRY_AFTER = 10.0
RAW_RESPONSE_LOG_LIMIT = 2000

FALLBACK_CHOICE = "rest"


@dataclass
class HttpResult:
    status: int
    headers: dict  # lower-case header names
    body: bytes


class TransportError(Exception):
    """The request never produced an HTTP response."""

    def __init__(self, message: str, timeout: bool = False):
        super().__init__(message)
        self.timeout = timeout


def urllib_transport(url: str, headers: dict, body: bytes, timeout: float) -> HttpResult:
    """POST with the standard library. Non-2xx responses are returned, not raised."""
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return HttpResult(response.status, {k.lower(): v for k, v in response.headers.items()}, response.read())
    except urllib.error.HTTPError as error:
        return HttpResult(error.code, {k.lower(): v for k, v in error.headers.items()}, error.read())
    except (socket.timeout, TimeoutError):
        raise TransportError("request timed out", timeout=True) from None
    except urllib.error.URLError as error:
        if isinstance(error.reason, (socket.timeout, TimeoutError)):
            raise TransportError("request timed out", timeout=True) from None
        raise TransportError(f"connection failed: {error.reason}") from None


class ResponseCache:
    """An optional on-disk cache of responses keyed by request body. Never used by `bench`."""

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self._entries: dict[str, dict] = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                for line in handle:
                    entry = json.loads(line)
                    self._entries[entry["key"]] = entry["response"]

    @staticmethod
    def key_for(body: bytes) -> str:
        return hashlib.sha256(body).hexdigest()

    def get(self, key: str):
        with self._lock:
            return self._entries.get(key)

    def put(self, key: str, response: dict) -> None:
        with self._lock:
            self._entries[key] = response
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps({"key": key, "response": response}) + "\n")


@dataclass
class _Totals:
    decisions: int = 0
    requests: int = 0
    fallbacks: int = 0
    retries: int = 0
    cache_hits: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    latencies_ms: list = field(default_factory=list)


class SystemOneBrain(Brain):
    def __init__(self, name: str, base_url: str, model: str, api_key: str | None = None,
                 batch: int = DEFAULT_BATCH, workers: int = DEFAULT_WORKERS, timeout: float = DEFAULT_TIMEOUT,
                 log_path: str | None = None, transport=urllib_transport, sleep=time.sleep,
                 max_retries: int = MAX_RETRIES, backoff: float = BACKOFF_SECONDS,
                 cache: ResponseCache | None = None):
        if batch < 1 or workers < 1:
            raise ValueError("batch and workers must be at least 1")
        self.name = name
        self.url = base_url.rstrip("/") + ENDPOINT
        self.model = model
        self._api_key = api_key
        self.batch = batch
        self.workers = workers
        self.timeout = timeout
        self.log_path = log_path
        self._transport = transport
        self._sleep = sleep
        self.max_retries = max_retries
        self.backoff = backoff
        self.cache = cache
        self._totals = _Totals()
        self._lock = threading.Lock()
        self._log_lock = threading.Lock()
        self._log_handle = None

    # -- public -----------------------------------------------------------

    def decide(self, requests: list[DecisionRequest], step: int = 0) -> list[Decision]:
        chunks = [requests[i:i + self.batch] for i in range(0, len(requests), self.batch)]
        if len(chunks) <= 1 or self.workers == 1:
            results = [self._call(chunk, step) for chunk in chunks]
        else:
            with ThreadPoolExecutor(max_workers=min(self.workers, len(chunks))) as pool:
                results = list(pool.map(lambda chunk: self._call(chunk, step), chunks))
        return [decision for chunk_result in results for decision in chunk_result]

    def summary(self) -> dict:
        with self._lock:
            totals = self._totals
            return {
                "decisions": totals.decisions, "requests": totals.requests, "fallbacks": totals.fallbacks,
                "retries": totals.retries, "cache_hits": totals.cache_hits,
                "input_tokens": totals.input_tokens, "output_tokens": totals.output_tokens,
                "latencies_ms": list(totals.latencies_ms),
            }

    def close(self) -> None:
        with self._log_lock:
            if self._log_handle is not None:
                self._log_handle.close()
                self._log_handle = None

    # -- one request ------------------------------------------------------

    def build_body(self, chunk: list[DecisionRequest]) -> dict:
        """The request body for one creature, or for a batch (spec 7.3)."""
        if len(chunk) == 1:
            request = chunk[0]
            state = request.view
            questions = {SINGLE_QUESTION_ID: {"type": "choice", "instructions": INSTRUCTIONS,
                                              "criteria": request.options}}
        else:
            state = {"creatures": {r.creature_id: r.view for r in chunk}}
            questions = {
                r.creature_id: {
                    "type": "choice",
                    "instructions": f"{INSTRUCTIONS} {BATCH_SENTENCE.format(id=r.creature_id)}",
                    "criteria": r.options,
                }
                for r in chunk
            }
        return {"model": self.model, "state": state, "questions": questions}

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _call(self, chunk: list[DecisionRequest], step: int) -> list[Decision]:
        body = self.build_body(chunk)
        payload = json.dumps(body).encode("utf-8")
        cache_key = ResponseCache.key_for(payload) if self.cache is not None else None

        response_json, raw_text, error, request_id, latency_ms, attempts, cached = None, None, None, None, 0.0, 0, False
        if cache_key is not None and (hit := self.cache.get(cache_key)) is not None:
            response_json, cached = hit, True
        else:
            result, error, latency_ms, attempts = self._send(payload)
            if result is not None:
                request_id = result.headers.get(REQUEST_ID_HEADER)
                raw_text = result.body.decode("utf-8", errors="replace")
                if 200 <= result.status < 300:
                    try:
                        response_json = json.loads(raw_text)
                    except ValueError:
                        error = "response was not valid JSON"
                else:
                    error = f"HTTP {result.status}"
            if response_json is not None and cache_key is not None:
                self.cache.put(cache_key, response_json)

        decisions = self._read_answers(chunk, response_json, latency_ms)
        self._count(chunk, decisions, response_json, latency_ms, attempts, cached)
        self._log(step, latency_ms, request_id, body, response_json if response_json is not None else raw_text,
                  error, attempts, cached)
        return decisions

    def _send(self, payload: bytes):
        """POST with up to `max_retries` retries on 429, 5xx and timeouts. Returns (result, error, ms, attempts)."""
        attempts = 0
        while True:
            attempts += 1
            started = time.perf_counter()
            result, error, retry_after = None, None, None
            try:
                result = self._transport(self.url, self._headers(), payload, self.timeout)
            except TransportError as exc:
                error = self._redact(str(exc))
                retriable = exc.timeout
            else:
                retriable = result.status == 429 or result.status >= 500
                retry_after = result.headers.get("retry-after")
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            if not retriable or attempts > self.max_retries:
                return result, error, elapsed_ms, attempts
            with self._lock:
                self._totals.retries += 1
            self._sleep(self._delay(attempts, retry_after))

    def _delay(self, attempts: int, retry_after) -> float:
        if retry_after is not None:
            try:
                return min(float(retry_after), MAX_RETRY_AFTER)
            except ValueError:
                pass
        return self.backoff * (2 ** (attempts - 1))

    # -- reading answers --------------------------------------------------

    def _read_answers(self, chunk, response_json, latency_ms) -> list[Decision]:
        answers = response_json.get("answers") if isinstance(response_json, dict) else None
        single = len(chunk) == 1
        decisions = []
        for request in chunk:
            answer = answers.get(SINGLE_QUESTION_ID if single else request.creature_id) if isinstance(answers, dict) else None
            decisions.append(self._to_decision(answer, request.options, latency_ms) or self._fallback(latency_ms))
        return decisions

    @staticmethod
    def _to_decision(answer, options: dict, latency_ms: float) -> Decision | None:
        """Accept an answer only if it is a `choice` for one of the options with usable probabilities."""
        if not isinstance(answer, dict) or answer.get("type") != "choice":
            return None
        choice = answer.get("choice")
        if not isinstance(choice, str) or choice not in options:
            return None
        probabilities = answer.get("probabilities")
        confidence = answer.get("confidence")
        if not isinstance(probabilities, dict) or not probabilities:
            return None
        clean = {}
        for key, value in probabilities.items():
            if key not in options or isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                return None
            clean[key] = float(value)
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            return None
        return Decision(choice, clean, min(1.0, max(0.0, float(confidence))), "model", latency_ms)

    @staticmethod
    def _fallback(latency_ms: float) -> Decision:
        return Decision(FALLBACK_CHOICE, {FALLBACK_CHOICE: 1.0}, 0.0, "fallback", latency_ms)

    # -- bookkeeping ------------------------------------------------------

    def _count(self, chunk, decisions, response_json, latency_ms, attempts, cached) -> None:
        usage = response_json.get("usage") if isinstance(response_json, dict) else None
        with self._lock:
            totals = self._totals
            totals.decisions += len(chunk)
            totals.fallbacks += sum(1 for d in decisions if d.source == "fallback")
            if cached:
                totals.cache_hits += 1
                return
            totals.requests += 1
            totals.latencies_ms.append(latency_ms)
            if isinstance(usage, dict):
                for key, attribute in (("input_tokens", "input_tokens"), ("output_tokens", "output_tokens")):
                    value = usage.get(key)
                    if isinstance(value, int) and not isinstance(value, bool):
                        setattr(totals, attribute, getattr(totals, attribute) + value)

    def _redact(self, text: str) -> str:
        if self._api_key:
            text = text.replace(self._api_key, "[redacted]")
        return text

    def _log(self, step, latency_ms, request_id, request, response, error, attempts, cached) -> None:
        if not self.log_path:
            return
        if isinstance(response, str):
            response = self._redact(response[:RAW_RESPONSE_LOG_LIMIT])
        line = {"brain": self.name, "step": step, "latency_ms": round(latency_ms, 1), "request_id": request_id,
                "request": request, "response": response, "error": self._redact(error) if error else None,
                "attempts": attempts}
        if cached:
            line["cached"] = True
        text = self._redact(json.dumps(line))
        with self._log_lock:
            if self._log_handle is None:
                os.makedirs(os.path.dirname(self.log_path) or ".", exist_ok=True)
                self._log_handle = open(self.log_path, "a", encoding="utf-8")
            self._log_handle.write(text + "\n")
            self._log_handle.flush()


def make_system_one_brain(spec: str, batch: int = DEFAULT_BATCH, workers: int = DEFAULT_WORKERS,
                          timeout: float = DEFAULT_TIMEOUT, log_path: str | None = None,
                          cache_path: str | None = None, **overrides) -> SystemOneBrain:
    """Configure a brain from the environment (spec 7.3). Keys are read from environment variables only."""
    env = os.environ
    if spec == "jev":
        api_key = env.get("TYPESAFE_API_KEY")
        if not api_key:
            raise RuntimeError("TYPESAFE_API_KEY is not set. Export it before using the jev brain.")
        name = "jev"
        base_url = env.get("TYPESAFE_BASE_URL") or "https://api.typesafe.ai"
        model = env.get("TYPESAFE_MODEL") or "jev-latest"
    elif spec.startswith("system-one@"):
        location = spec[len("system-one@"):]
        base_url, _, model = location.partition("#")
        if not base_url or not model:
            raise ValueError("use system-one@BASE_URL#MODEL")
        name = "system-one"
        api_key = env.get("SYSTEM_ONE_API_KEY") or None
    else:
        raise ValueError(f"not a System One brain: {spec!r}")
    cache = ResponseCache(cache_path) if cache_path else None
    return SystemOneBrain(name, base_url, model, api_key, batch=batch, workers=workers, timeout=timeout,
                          log_path=log_path, cache=cache, **overrides)
