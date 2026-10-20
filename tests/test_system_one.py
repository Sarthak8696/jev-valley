import json
import threading
import time

import pytest

from valley.brains import make_brain
from valley.brains.base import DecisionRequest
from valley.brains.system_one import (
    BATCH_SENTENCE, INSTRUCTIONS, HttpResult, ResponseCache, SystemOneBrain, TransportError,
    make_system_one_brain,
)
from valley.species import action_menu

KEY = "sk-test-SECRET-123"
OPTIONS = action_menu("rabbit")


def request(cid="r1", **view):
    return DecisionRequest(cid, {"id": cid, "animal": f"{cid} the rabbit", **view}, dict(OPTIONS), {"energy": 0.5})


def answer(choice="eat", confidence=0.8, extra=None):
    probabilities = {option: 0.02 for option in OPTIONS}
    probabilities[choice] = 0.86
    body = {"type": "choice", "choice": choice, "probabilities": probabilities, "confidence": confidence}
    body.update(extra or {})
    return body


def ok(answers, usage=None, headers=None):
    payload = {"answers": answers}
    if usage is not None:
        payload["usage"] = usage
    return HttpResult(200, {k.lower(): v for k, v in (headers or {}).items()}, json.dumps(payload).encode())


class FakeTransport:
    """Records every call and answers from a handler(body, call_number) -> HttpResult, or raises."""

    def __init__(self, handler=None):
        self.calls = []
        self.handler = handler or self.default
        self._lock = threading.Lock()

    @staticmethod
    def default(body, n):
        return ok({qid: answer() for qid in body["questions"]})

    def __call__(self, url, headers, payload, timeout):
        body = json.loads(payload)
        with self._lock:
            self.calls.append({"url": url, "headers": headers, "body": body, "timeout": timeout})
            n = len(self.calls)
        result = self.handler(body, n)
        if isinstance(result, Exception):
            raise result
        return result


def brain(transport=None, **kwargs):
    kwargs.setdefault("sleep", lambda s: None)
    return SystemOneBrain("jev", "https://example.test", "jev-latest", KEY, transport=transport or FakeTransport(),
                          **kwargs)


# -- request shape ---------------------------------------------------------------

def test_single_request_body_matches_the_spec_exactly():
    t = FakeTransport()
    b = brain(t)
    r = request("r12", hunger="hungry")
    b.decide([r])
    call = t.calls[0]
    assert call["url"] == "https://example.test/v1/systemone"
    assert call["body"] == {
        "model": "jev-latest",
        "state": {"id": "r12", "animal": "r12 the rabbit", "hunger": "hungry"},
        "questions": {"action": {"type": "choice", "instructions": INSTRUCTIONS, "criteria": OPTIONS}},
    }
    assert list(call["body"]) == ["model", "state", "questions"]


def test_batched_request_body_matches_the_spec_exactly():
    t = FakeTransport()
    b = brain(t)
    rs = [request("r12"), request("w3")]
    b.decide(rs)
    body = t.calls[0]["body"]
    assert body["state"] == {"creatures": {"r12": rs[0].view, "w3": rs[1].view}}
    assert list(body["questions"]) == ["r12", "w3"]
    for cid in ("r12", "w3"):
        q = body["questions"][cid]
        assert q["type"] == "choice" and q["criteria"] == OPTIONS
        assert q["instructions"] == INSTRUCTIONS + " " + BATCH_SENTENCE.format(id=cid)
    assert body["questions"]["r12"]["instructions"].endswith("Decide only for the creature with id 'r12', using creatures['r12'].")


def test_the_instruction_has_no_time_of_day():
    assert "time of day" not in INSTRUCTIONS
    assert INSTRUCTIONS.startswith("You are deciding the next action of one wild animal in a valley for the coming hour.")


def test_headers_carry_the_key_only_in_authorization():
    t = FakeTransport()
    brain(t).decide([request()])
    headers = t.calls[0]["headers"]
    assert headers == {"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"}
    assert KEY not in json.dumps(t.calls[0]["body"])


def test_no_authorization_header_without_a_key():
    t = FakeTransport()
    SystemOneBrain("laya", "http://localhost:8000", "laya-auto", None, transport=t).decide([request()])
    assert t.calls[0]["headers"] == {"Content-Type": "application/json"}
    assert t.calls[0]["url"] == "http://localhost:8000/v1/systemone"


def test_a_trailing_slash_on_the_base_url_is_ignored():
    b = SystemOneBrain("x", "http://host/", "m", None, transport=FakeTransport())
    assert b.url == "http://host/v1/systemone"


def test_the_timeout_setting_is_passed_to_the_transport():
    t = FakeTransport()
    brain(t, timeout=7).decide([request()])
    assert t.calls[0]["timeout"] == 7


# -- chunking ----------------------------------------------------------------------

def test_requests_are_split_into_batches_and_order_is_kept():
    t = FakeTransport()
    b = brain(t, batch=8)
    rs = [request(f"r{i}") for i in range(20)]
    decisions = b.decide(rs)
    assert sorted(len(c["body"]["questions"]) for c in t.calls) == [4, 8, 8]
    assert len(decisions) == 20


def test_a_batch_of_one_uses_the_single_question_form():
    t = FakeTransport()
    brain(t, batch=8).decide([request(f"r{i}") for i in range(9)])
    forms = sorted("action" in c["body"]["questions"] for c in t.calls)
    assert forms == [False, True]


def test_decisions_come_back_in_request_order_even_when_responses_finish_out_of_order():
    def handler(body, n):
        creature = body["state"]["id"]  # a batch of one uses the single-question form
        time.sleep(0.05 if creature == "r0" else 0.0)
        return ok({"action": answer(choice=("eat" if creature == "r0" else "drink"))})

    b = brain(FakeTransport(handler), batch=1, workers=4)
    decisions = b.decide([request("r0"), request("r1"), request("r2")])
    assert [d.choice for d in decisions] == ["eat", "drink", "drink"]


def test_a_chunk_request_uses_the_question_id_of_each_creature_to_read_answers():
    def handler(body, n):
        return ok({qid: answer(choice=("flee" if qid == "r2" else "eat")) for qid in body["questions"]})

    decisions = brain(FakeTransport(handler)).decide([request("r1"), request("r2")])
    assert [d.choice for d in decisions] == ["eat", "flee"]


# -- reading answers --------------------------------------------------------------------

def test_a_valid_answer_is_parsed():
    t = FakeTransport(lambda body, n: ok({"action": answer("flee", 0.77)}, usage={"input_tokens": 120, "output_tokens": 9}))
    b = brain(t)
    [d] = b.decide([request()])
    assert (d.choice, d.confidence, d.source) == ("flee", 0.77, "model")
    assert d.probabilities["flee"] == 0.86 and set(d.probabilities) == set(OPTIONS)
    assert d.latency_ms is not None and d.latency_ms >= 0
    summary = b.summary()
    assert summary["input_tokens"] == 120 and summary["output_tokens"] == 9
    assert summary["decisions"] == 1 and summary["requests"] == 1 and summary["fallbacks"] == 0


def bad_answer_cases():
    good = answer()
    return {
        "missing": None,
        "wrong type": dict(good, type="score"),
        "choice not an option": dict(good, choice="dance"),
        "choice not a string": dict(good, choice=3),
        "no probabilities": {k: v for k, v in good.items() if k != "probabilities"},
        "empty probabilities": dict(good, probabilities={}),
        "unknown option in probabilities": dict(good, probabilities={"dance": 1.0}),
        "negative probability": dict(good, probabilities={"eat": -0.1}),
        "non numeric probability": dict(good, probabilities={"eat": "high"}),
        "no confidence": {k: v for k, v in good.items() if k != "confidence"},
        "bool confidence": dict(good, confidence=True),
        "not an object": "eat",
    }


@pytest.mark.parametrize("case", list(bad_answer_cases()))
def test_missing_or_invalid_answers_become_fallbacks(case):
    bad = bad_answer_cases()[case]
    answers = {} if bad is None else {"action": bad}
    b = brain(FakeTransport(lambda body, n: ok(answers)))
    [d] = b.decide([request()])
    assert (d.choice, d.probabilities, d.confidence, d.source) == ("rest", {"rest": 1.0}, 0.0, "fallback")
    assert b.summary()["fallbacks"] == 1


def test_only_the_bad_answer_in_a_batch_falls_back():
    def handler(body, n):
        return ok({"r1": answer("eat"), "r2": {"type": "choice", "choice": "nope"}, "r3": answer("hide")})

    decisions = brain(FakeTransport(handler)).decide([request("r1"), request("r2"), request("r3")])
    assert [(d.choice, d.source) for d in decisions] == [("eat", "model"), ("rest", "fallback"), ("hide", "model")]


def test_confidence_outside_zero_to_one_is_clamped():
    t = FakeTransport(lambda body, n: ok({"action": answer("eat", 1.7)}))
    assert brain(t).decide([request()])[0].confidence == 1.0


def test_malformed_json_is_a_fallback_and_logged_as_an_error(tmp_path):
    log = tmp_path / "requests.jsonl"
    t = FakeTransport(lambda body, n: HttpResult(200, {}, b"<html>oops</html>"))
    b = brain(t, log_path=str(log))
    assert b.decide([request()])[0].source == "fallback"
    b.close()
    line = json.loads(log.read_text().splitlines()[0])
    assert line["error"] == "response was not valid JSON" and line["response"] == "<html>oops</html>"


def test_usage_is_optional():
    b = brain(FakeTransport(lambda body, n: ok({"action": answer()})))
    b.decide([request()])
    assert b.summary()["input_tokens"] == 0


# -- failures and retries ---------------------------------------------------------------

def test_a_client_error_falls_back_without_retrying():
    t = FakeTransport(lambda body, n: HttpResult(400, {}, b'{"error":"bad"}'))
    sleeps = []
    b = brain(t, sleep=sleeps.append)
    decisions = b.decide([request("r1"), request("r2")])
    assert [d.source for d in decisions] == ["fallback", "fallback"]
    assert len(t.calls) == 1 and sleeps == []
    assert b.summary()["retries"] == 0 and b.summary()["fallbacks"] == 2


def test_a_server_error_is_retried_twice_with_backoff_and_then_falls_back():
    t = FakeTransport(lambda body, n: HttpResult(503, {}, b"down"))
    sleeps = []
    b = brain(t, sleep=sleeps.append)
    [d] = b.decide([request()])
    assert d.source == "fallback"
    assert len(t.calls) == 3
    assert sleeps == [0.5, 1.0]
    assert b.summary()["retries"] == 2


def test_a_429_is_retried_and_can_then_succeed():
    def handler(body, n):
        return HttpResult(429, {}, b"slow down") if n == 1 else ok({"action": answer("eat")})

    t = FakeTransport(handler)
    b = brain(t)
    [d] = b.decide([request()])
    assert d.source == "model" and len(t.calls) == 2
    assert b.summary()["retries"] == 1 and b.summary()["fallbacks"] == 0


def test_retry_after_is_honoured_up_to_a_limit():
    t = FakeTransport(lambda body, n: HttpResult(429, {"retry-after": "3"}, b"") if n == 1 else
                      HttpResult(429, {"retry-after": "999"}, b"") if n == 2 else ok({"action": answer()}))
    sleeps = []
    brain(t, sleep=sleeps.append).decide([request()])
    assert sleeps == [3.0, 10.0]


def test_a_timeout_is_retried():
    def handler(body, n):
        return TransportError("request timed out", timeout=True) if n < 3 else ok({"action": answer()})

    t = FakeTransport(handler)
    b = brain(t)
    assert b.decide([request()])[0].source == "model"
    assert len(t.calls) == 3 and b.summary()["retries"] == 2


def test_other_connection_errors_are_not_retried():
    t = FakeTransport(lambda body, n: TransportError("connection failed: refused"))
    b = brain(t)
    assert b.decide([request()])[0].source == "fallback"
    assert len(t.calls) == 1 and b.summary()["retries"] == 0


def test_a_failed_request_marks_every_creature_in_the_batch_as_a_fallback():
    t = FakeTransport(lambda body, n: HttpResult(500, {}, b""))
    b = brain(t, max_retries=0)
    decisions = b.decide([request(f"r{i}") for i in range(5)])
    assert all(d.source == "fallback" for d in decisions)
    assert b.summary()["fallbacks"] == 5 and b.summary()["decisions"] == 5


# -- the log and secrets ----------------------------------------------------------------

def test_requests_jsonl_lines_have_the_documented_fields(tmp_path):
    log = tmp_path / "logs" / "requests.jsonl"
    t = FakeTransport(lambda body, n: ok({"action": answer()}, headers={"X-TypeSafe-Request-Id": "req_abc"}))
    b = brain(t, log_path=str(log))
    b.decide([request()], step=12)
    b.close()
    [line] = [json.loads(x) for x in log.read_text().splitlines()]
    assert set(line) == {"brain", "step", "latency_ms", "request_id", "request", "response", "error", "attempts"}
    assert line["brain"] == "jev" and line["step"] == 12 and line["request_id"] == "req_abc"
    assert line["request"]["model"] == "jev-latest" and "answers" in line["response"]
    assert line["error"] is None and line["attempts"] == 1


def test_request_id_is_null_without_the_header(tmp_path):
    log = tmp_path / "r.jsonl"
    b = brain(FakeTransport(), log_path=str(log))
    b.decide([request()])
    b.close()
    assert json.loads(log.read_text().splitlines()[0])["request_id"] is None


def test_the_api_key_never_appears_in_the_log_or_in_errors(tmp_path):
    log = tmp_path / "requests.jsonl"
    leaky = TransportError(f"proxy rejected Bearer {KEY}")
    b = brain(FakeTransport(lambda body, n: leaky), log_path=str(log))
    decisions = b.decide([request()])
    b.close()
    text = log.read_text()
    assert KEY not in text and "[redacted]" in text
    assert KEY not in json.dumps([d.__dict__ for d in decisions])
    assert KEY not in json.dumps(b.summary())


def test_the_key_is_redacted_even_if_a_server_echoes_it(tmp_path):
    log = tmp_path / "requests.jsonl"
    t = FakeTransport(lambda body, n: HttpResult(401, {}, f"invalid key {KEY}".encode()))
    b = brain(t, log_path=str(log))
    b.decide([request()])
    b.close()
    assert KEY not in log.read_text()


def test_no_log_is_written_unless_asked_for(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    brain(FakeTransport()).decide([request()])
    assert list(tmp_path.iterdir()) == []


# -- totals ------------------------------------------------------------------------------

def test_summary_totals_add_up_across_requests():
    t = FakeTransport(lambda body, n: ok({qid: answer() for qid in body["questions"]},
                                         usage={"input_tokens": 100, "output_tokens": 10}))
    b = brain(t, batch=4)
    b.decide([request(f"r{i}") for i in range(10)])
    s = b.summary()
    assert s["decisions"] == 10 and s["requests"] == 3
    assert s["input_tokens"] == 300 and s["output_tokens"] == 30
    assert len(s["latencies_ms"]) == 3 and s["retries"] == 0


# -- the optional cache -----------------------------------------------------------------

def test_the_cache_skips_repeat_requests(tmp_path):
    path = tmp_path / "cache.jsonl"
    t = FakeTransport()
    b = brain(t, cache=ResponseCache(str(path)))
    first = b.decide([request()])
    second = b.decide([request()])
    assert len(t.calls) == 1
    assert first[0].choice == second[0].choice
    assert b.summary()["cache_hits"] == 1 and b.summary()["requests"] == 1
    t2 = FakeTransport()
    b2 = brain(t2, cache=ResponseCache(str(path)))  # a new run loads the file
    b2.decide([request()])
    assert t2.calls == []


def test_there_is_no_cache_by_default():
    t = FakeTransport()
    b = brain(t)
    b.decide([request()])
    b.decide([request()])
    assert len(t.calls) == 2 and b.cache is None


# -- configuration from the environment -------------------------------------------------

ENV_NAMES = ["TYPESAFE_API_KEY", "TYPESAFE_BASE_URL", "TYPESAFE_MODEL", "LAYA_BASE_URL", "LAYA_MODEL",
             "LAYA_API_KEY", "SYSTEM_ONE_API_KEY"]


@pytest.fixture
def clean_env(monkeypatch):
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_jev_needs_an_api_key(clean_env):
    with pytest.raises(RuntimeError, match="TYPESAFE_API_KEY"):
        make_brain("jev")


def test_jev_defaults_and_overrides(clean_env):
    clean_env.setenv("TYPESAFE_API_KEY", KEY)
    b = make_brain("jev")
    assert b.name == "jev" and b.url == "https://api.typesafe.ai/v1/systemone" and b.model == "jev-latest"
    clean_env.setenv("TYPESAFE_BASE_URL", "https://gateway.test")
    clean_env.setenv("TYPESAFE_MODEL", "jev-2")
    b = make_brain("jev", batch=10, workers=2, timeout=5)
    assert b.url == "https://gateway.test/v1/systemone" and b.model == "jev-2"
    assert (b.batch, b.workers, b.timeout) == (10, 2, 5)


def test_laya_defaults_and_optional_key(clean_env):
    b = make_brain("laya")
    assert b.name == "laya" and b.url == "http://localhost:8000/v1/systemone" and b.model == "laya-auto"
    assert b._headers() == {"Content-Type": "application/json"}
    clean_env.setenv("LAYA_BASE_URL", "http://localhost:9000")
    clean_env.setenv("LAYA_MODEL", "laya-small")
    clean_env.setenv("LAYA_API_KEY", "k")
    b = make_brain("laya")
    assert b.url == "http://localhost:9000/v1/systemone" and b.model == "laya-small"
    assert b._headers()["Authorization"] == "Bearer k"


def test_other_servers_use_the_system_one_spec(clean_env):
    b = make_brain("system-one@http://example.test:1234#my-model")
    assert b.url == "http://example.test:1234/v1/systemone" and b.model == "my-model" and b.name == "system-one"
    with pytest.raises(ValueError):
        make_brain("system-one@http://example.test")


def test_unknown_brains_are_rejected():
    with pytest.raises(ValueError):
        make_brain("gpt")


def test_the_log_path_and_cache_path_are_passed_through(clean_env, tmp_path):
    clean_env.setenv("TYPESAFE_API_KEY", KEY)
    b = make_system_one_brain("jev", log_path=str(tmp_path / "x.jsonl"), cache_path=str(tmp_path / "c.jsonl"))
    assert b.log_path.endswith("x.jsonl") and b.cache is not None
