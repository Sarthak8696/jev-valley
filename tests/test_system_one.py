import json
import threading
import time

import pytest

from valley.brains import make_brain
from valley.brains.base import DecisionError, DecisionRequest, Question
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
    SystemOneBrain("local", "http://localhost:8000", "local-model", None, transport=t).decide([request()])
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
    assert summary["decisions"] == 1 and summary["requests"] == 1 and "fallbacks" not in summary


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
def test_a_missing_or_invalid_answer_stops_the_run(case):
    bad = bad_answer_cases()[case]
    answers = {} if bad is None else {"action": bad}
    b = brain(FakeTransport(lambda body, n: ok(answers)))
    with pytest.raises(DecisionError, match="r1"):
        b.decide([request()])
    assert b.summary()["decisions"] == 0  # nothing was accepted


def test_one_bad_answer_in_a_batch_stops_the_run_and_names_the_animal():
    def handler(body, n):
        return ok({"r1": answer("eat"), "r2": {"type": "choice", "choice": "nope"}, "r3": answer("hide")})

    with pytest.raises(DecisionError, match=r"answer for r2 is unusable: choice 'nope' is not one of the options"):
        brain(FakeTransport(handler)).decide([request("r1"), request("r2"), request("r3")])


def test_a_response_without_answers_stops_the_run():
    with pytest.raises(DecisionError, match="no `answers` object"):
        brain(FakeTransport(lambda body, n: HttpResult(200, {}, b"{}"))).decide([request()])


def test_nothing_is_ever_decided_for_the_model():
    """No code path returns a decision the model did not give."""
    import valley.brains.system_one as module
    assert not hasattr(module, "FALLBACK_CHOICE") and not hasattr(SystemOneBrain, "_fallback")


def test_confidence_outside_zero_to_one_is_clamped():
    t = FakeTransport(lambda body, n: ok({"action": answer("eat", 1.7)}))
    assert brain(t).decide([request()])[0].confidence == 1.0


def test_malformed_json_stops_the_run_and_is_logged_as_an_error(tmp_path):
    log = tmp_path / "requests.jsonl"
    t = FakeTransport(lambda body, n: HttpResult(200, {}, b"<html>oops</html>"))
    b = brain(t, log_path=str(log))
    with pytest.raises(DecisionError, match="not valid JSON"):
        b.decide([request()])
    b.close()
    line = json.loads(log.read_text().splitlines()[0])
    assert line["error"] == "the response was not valid JSON" and line["response"] == "<html>oops</html>"


def test_usage_is_optional():
    b = brain(FakeTransport(lambda body, n: ok({"action": answer()})))
    b.decide([request()])
    assert b.summary()["input_tokens"] == 0


# -- failures and retries ---------------------------------------------------------------

def test_a_client_error_stops_the_run_without_retrying_and_shows_the_servers_message():
    t = FakeTransport(lambda body, n: HttpResult(400, {}, b'{"error":"bad"}'))
    sleeps = []
    b = brain(t, sleep=sleeps.append)
    with pytest.raises(DecisionError, match=r"HTTP 400: .*bad"):
        b.decide([request("r1"), request("r2")])
    assert len(t.calls) == 1 and sleeps == []
    assert b.summary()["retries"] == 0


def test_an_unauthorised_key_stops_the_run_at_once():
    t = FakeTransport(lambda body, n: HttpResult(401, {}, b'{"error":"invalid api key"}'))
    with pytest.raises(DecisionError, match="HTTP 401"):
        brain(t).decide([request()])
    assert len(t.calls) == 1


def test_a_server_error_is_retried_twice_with_backoff_and_then_stops_the_run():
    t = FakeTransport(lambda body, n: HttpResult(503, {}, b"down"))
    sleeps = []
    b = brain(t, sleep=sleeps.append)
    with pytest.raises(DecisionError, match="HTTP 503"):
        b.decide([request()])
    assert len(t.calls) == 3
    assert sleeps == [0.5, 1.0]
    assert b.summary()["retries"] == 2


def test_with_no_retries_the_first_error_stops_the_run():
    t = FakeTransport(lambda body, n: HttpResult(429, {}, b"slow down"))
    with pytest.raises(DecisionError, match="HTTP 429"):
        brain(t, max_retries=0).decide([request()])
    assert len(t.calls) == 1


def test_a_429_is_retried_and_can_then_succeed():
    def handler(body, n):
        return HttpResult(429, {}, b"slow down") if n == 1 else ok({"action": answer("eat")})

    t = FakeTransport(handler)
    b = brain(t)
    [d] = b.decide([request()])
    assert d.source == "model" and len(t.calls) == 2
    assert b.summary()["retries"] == 1


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


def test_other_connection_errors_are_not_retried_and_stop_the_run():
    t = FakeTransport(lambda body, n: TransportError("connection failed: refused"))
    b = brain(t)
    with pytest.raises(DecisionError, match="connection failed: refused"):
        b.decide([request()])
    assert len(t.calls) == 1 and b.summary()["retries"] == 0


def test_a_failed_request_gives_no_decisions_at_all_for_its_batch():
    t = FakeTransport(lambda body, n: HttpResult(500, {}, b""))
    b = brain(t, max_retries=0)
    with pytest.raises(DecisionError):
        b.decide([request(f"r{i}") for i in range(5)])
    assert b.summary()["decisions"] == 0


def test_the_error_names_the_step_and_the_request_id():
    t = FakeTransport(lambda body, n: HttpResult(502, {"x-typesafe-request-id": "req_42"}, b"bad gateway"))
    with pytest.raises(DecisionError) as info:
        brain(t, max_retries=0).decide([request()], step=14)
    text = str(info.value)
    assert "step 14" in text and "Day 1, 8 pm" in text and "req_42" in text and "HTTP 502" in text


def test_a_rejected_answer_is_not_cached(tmp_path):
    cache = ResponseCache(str(tmp_path / "cache.jsonl"))
    b = brain(FakeTransport(lambda body, n: ok({"action": {"type": "choice", "choice": "nope"}})), cache=cache)
    with pytest.raises(DecisionError):
        b.decide([request()])
    assert not (tmp_path / "cache.jsonl").exists()


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
    with pytest.raises(DecisionError) as info:
        b.decide([request()])
    b.close()
    text = log.read_text()
    assert KEY not in text and "[redacted]" in text
    assert KEY not in str(info.value)
    assert KEY not in json.dumps(b.summary())


def test_the_key_is_redacted_even_if_a_server_echoes_it(tmp_path):
    log = tmp_path / "requests.jsonl"
    t = FakeTransport(lambda body, n: HttpResult(401, {}, f"invalid key {KEY}".encode()))
    b = brain(t, log_path=str(log))
    with pytest.raises(DecisionError) as info:
        b.decide([request()])
    b.close()
    assert KEY not in log.read_text() and KEY not in str(info.value)


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

ENV_NAMES = ["TYPESAFE_API_KEY", "TYPESAFE_BASE_URL", "TYPESAFE_MODEL", "SYSTEM_ONE_API_KEY"]


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


def test_a_generic_server_has_an_optional_key(clean_env):
    b = make_brain("system-one@http://localhost:9000#small")
    assert b._headers() == {"Content-Type": "application/json"}
    clean_env.setenv("SYSTEM_ONE_API_KEY", "k")
    b = make_brain("system-one@http://localhost:9000#small")
    assert b._headers()["Authorization"] == "Bearer k"


def test_laya_is_not_a_brain_any_more():
    with pytest.raises(ValueError):
        make_brain("laya")


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


# -- the extra score and noul questions of the rich mode ------------------------------------

LEVELS = ["calm", "relaxed", "watchful", "alert", "on guard"]
ALERT_Q = Question("alert", "score", "How alert should this animal be?", LEVELS)
BREED_Q = Question("breed", "noul", "Is now a good time to have young?", {"true": "yes", "false": "no"})
WEAK_Q = Question("weak:d4", "score", "How weak does Pip look?", LEVELS)


def rich_request(cid="r1", questions=None):
    r = request(cid)
    r.questions = list(questions if questions is not None else [ALERT_Q, BREED_Q])
    return r


def score_answer(value):
    return {"type": "score", "score": value, "confidence": 0.9, "legend": {str(i): t for i, t in enumerate(LEVELS)},
            "probabilities": {str(i): 0.2 for i in range(5)}}


def noul_answer(value):
    return {"type": "noul", "noul": value}


def rich_handler(overrides=None):
    """Answers every question by its type, with `overrides` (question id -> answer, or None to leave it out)."""
    def handle(body, n):
        answers = {}
        for qid, question in body["questions"].items():
            answers[qid] = {"choice": lambda: answer(), "score": lambda: score_answer(3.2), "noul": lambda: noul_answer(0.25)}[question["type"]]()
        for qid, replacement in (overrides or {}).items():
            if replacement is None:
                answers.pop(qid, None)
            else:
                answers[qid] = replacement
        return ok(answers)
    return handle


def test_a_single_request_carries_the_extra_questions_with_plain_ids():
    t = FakeTransport(rich_handler())
    brain(t).decide([rich_request("r1")])
    questions = t.calls[0]["body"]["questions"]
    assert list(questions) == ["action", "alert", "breed"]
    assert questions["alert"] == {"type": "score", "instructions": ALERT_Q.instructions, "criteria": LEVELS}
    assert questions["breed"] == {"type": "noul", "instructions": BREED_Q.instructions, "criteria": {"true": "yes", "false": "no"}}
    assert questions["action"]["type"] == "choice"


def test_a_batch_names_each_extra_question_after_its_creature():
    t = FakeTransport(rich_handler())
    wolf = rich_request("w1", [WEAK_Q, BREED_Q])
    brain(t).decide([rich_request("r1"), wolf])
    questions = t.calls[0]["body"]["questions"]
    assert list(questions) == ["r1", "w1", "r1.alert", "r1.breed", "w1.weak.d4", "w1.breed"]
    sentence = BATCH_SENTENCE.format(id="w1")
    assert questions["w1.weak.d4"]["instructions"] == f"{WEAK_Q.instructions} {sentence}"
    assert questions["r1.alert"]["instructions"].endswith(BATCH_SENTENCE.format(id="r1"))


def test_score_and_noul_answers_come_back_as_numbers_by_question_key():
    t = FakeTransport(rich_handler({"r2.alert": score_answer(4.0), "r2.breed": noul_answer(1.0)}))
    first, second = brain(t).decide([rich_request("r1"), rich_request("r2")])
    assert first.extras == {"alert": 3.2, "breed": 0.25}
    assert second.extras == {"alert": 4.0, "breed": 1.0}
    assert first.choice == "eat"


def test_a_score_a_hair_outside_its_levels_is_clamped_but_a_real_overshoot_is_an_error():
    t = FakeTransport(rich_handler({"alert": score_answer(4.0000001)}))
    assert brain(t).decide([rich_request("r1")])[0].extras["alert"] == 4.0
    with pytest.raises(DecisionError, match="outside 0 to 4"):
        brain(FakeTransport(rich_handler({"alert": score_answer(4.5)}))).decide([rich_request("r1")])


@pytest.mark.parametrize("override, message", [
    ({"alert": None}, "it is missing"),
    ({"alert": noul_answer(0.5)}, "not a `score` answer"),
    ({"breed": score_answer(1.0)}, "not a `noul` answer"),
    ({"breed": noul_answer(1.4)}, "outside 0 to 1"),
    ({"breed": noul_answer(-0.2)}, "outside 0 to 1"),
    ({"breed": {"type": "noul", "noul": "yes"}}, "not a number"),
    ({"breed": {"type": "noul", "noul": True}}, "not a number"),
    ({"alert": {"type": "score", "confidence": 0.5}}, "not a number"),
])
def test_a_missing_or_invalid_extra_answer_stops_the_run(override, message):
    with pytest.raises(DecisionError) as error:
        brain(FakeTransport(rich_handler(override))).decide([rich_request("r1")])
    assert message in str(error.value)
    assert "r1" in str(error.value)


def test_an_extra_answer_that_is_wrong_in_a_batch_names_the_creature_and_the_question():
    t = FakeTransport(rich_handler({"w1.weak.d4": noul_answer(0.5)}))
    with pytest.raises(DecisionError, match=r"'weak:d4' answer for w1 is unusable"):
        brain(t).decide([rich_request("r1"), rich_request("w1", [WEAK_Q])])


def test_a_response_captured_from_the_real_api_is_read_correctly():
    """The answers the live Jev API gave on 2026-10-25 to a choice, a score and a noul question in one request."""
    real = {"model": "jev-1.14.0", "answers": {
        "action": {"type": "choice", "choice": "flee", "confidence": 0.53, "probabilities": {"eat": 0.25, "flee": 0.65, "hide": 0.1, "rest": 0.0}},
        "alert": {"type": "score", "score": 3.88, "confidence": 0.92,
                  "legend": {"0": "a", "1": "b", "2": "c", "3": "d", "4": "e"},
                  "probabilities": {"0": 0.0, "1": 0.0, "2": 0.0, "3": 0.1, "4": 0.9}},
        "breed": {"type": "noul", "noul": 0.04}}, "usage": {"input_tokens": 586, "output_tokens": 78}}

    def handler(body, n):
        return HttpResult(200, {}, json.dumps(real).encode())

    r = DecisionRequest("r1", {"id": "r1"}, {"eat": "", "flee": "", "hide": "", "rest": ""}, {}, [ALERT_Q, BREED_Q])
    decision = brain(FakeTransport(handler)).decide([r])[0]
    assert (decision.choice, decision.confidence) == ("flee", 0.53)
    assert decision.extras == {"alert": 3.88, "breed": 0.04}


def test_the_extra_questions_are_logged_with_the_request(tmp_path):
    log = tmp_path / "requests.jsonl"
    b = brain(FakeTransport(rich_handler()), log_path=str(log))
    b.decide([rich_request("r1")])
    b.close()
    line = json.loads(log.read_text().splitlines()[0])
    assert set(line["request"]["questions"]) == {"action", "alert", "breed"}
    assert line["response"]["answers"]["breed"] == {"type": "noul", "noul": 0.25}
