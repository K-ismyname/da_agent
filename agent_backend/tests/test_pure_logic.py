# LLM 없이 검증 가능한 순수 로직 테스트 — _extract_json, Evaluator 스코어링,
# Supervisor fallback, graph.py 라우팅 방어 로직
import pytest

from agent_backend.agents.nodes import _extract_json, node_evaluator, node_supervisor
from agent_backend.graph import _route, _trust_gate


# ── _extract_json ─────────────────────────────────────────────────────
def test_extract_plain_json():
    assert _extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_block():
    assert _extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_bare_block():
    assert _extract_json('```\n{"a": 1}\n```') == {"a": 1}


def test_extract_with_surrounding_text():
    assert _extract_json('Here is the result:\n{"a": 1}\nDone.') == {"a": 1}


def test_extract_invalid_raises():
    with pytest.raises(Exception):
        _extract_json("no json here")


# ── Evaluator 스코어링 ────────────────────────────────────────────────
def _run_evaluator(numeric, statements, monkeypatch):
    import agent_backend.agents.nodes as nodes
    monkeypatch.setattr(nodes, "_judge_claims", lambda state: {
        "numeric_checks": numeric,
        "statement_checks": statements,
        "evidence_sources": [],
    })
    return nodes.node_evaluator({})["evaluation"]


def test_all_pass_gives_full_confidence(monkeypatch):
    ev = _run_evaluator(
        [{"result": "PASS"}, {"result": "PASS"}],
        [{"judgment": "YES"}],
        monkeypatch,
    )
    assert ev["confidence"] == 100.0
    assert ev["hallucination_risk"] == 0.0
    assert ev["verdict"] == "PASS"


def test_all_fail_gives_fail_verdict(monkeypatch):
    ev = _run_evaluator([{"result": "FAIL"}], [{"judgment": "NO"}], monkeypatch)
    assert ev["confidence"] == 0.0
    assert ev["verdict"] == "FAIL"


def test_missing_keys_do_not_crash(monkeypatch):
    # LLM이 키를 빠뜨려도 크래시 대신 FAIL로 집계돼야 한다
    ev = _run_evaluator([{}, {"result": "PASS"}], [{}], monkeypatch)
    assert ev["checks"]["fail"] == 2
    assert ev["verdict"] == "FAIL"


def test_empty_checks_fail(monkeypatch):
    ev = _run_evaluator([], [], monkeypatch)
    assert ev["confidence"] == 0.0
    assert ev["verdict"] == "FAIL"


def test_risk_ignores_dimension_with_no_claims(monkeypatch):
    # 회귀 방지: 정성 주장만 있고(전부 YES) 숫자 주장이 아예 없으면, 예전엔
    # grounded_numeric=0이 평균을 끌어내려 risk=50(WARN)이 나오던 버그가 있었다.
    # 검증한 차원(정성)만 평균에 들어가야 risk=0이 맞다.
    ev = _run_evaluator([], [{"judgment": "YES"}, {"judgment": "YES"}], monkeypatch)
    assert ev["grounded_llm"] == 100.0
    assert ev["hallucination_risk"] == 0.0
    assert ev["verdict"] == "PASS"


def test_risk_ignores_dimension_with_no_statements(monkeypatch):
    # 대칭 케이스: 숫자 주장만 있고 정성 주장이 없어도 마찬가지로 risk=0이어야 한다.
    ev = _run_evaluator([{"result": "PASS"}, {"result": "PASS"}], [], monkeypatch)
    assert ev["grounded_numeric"] == 100.0
    assert ev["hallucination_risk"] == 0.0
    assert ev["verdict"] == "PASS"


# ── LLM 호출 헬퍼 실패 방어 (_invoke_json) ──────────────────────────
class _FakeLLM:
    """llm 객체를 통째로 대체하는 가짜 — invoke가 예외를 던지거나 지정 content를
    반환하게 해서, 실제 OpenAI 호출 없이 실패 방어를 검증한다."""
    def __init__(self, content=None, exc=None):
        self._content, self._exc = content, exc

    def invoke(self, messages):
        if self._exc:
            raise self._exc
        return type("M", (), {"content": self._content})()

    def bind_tools(self, tools):
        return self


def test_invoke_json_returns_error_dict_on_exception(monkeypatch):
    # LLM 호출이 실패(rate limit 등)해도 예외를 던지지 않고 error dict를 반환해야 한다.
    import agent_backend.agents.nodes as nodes
    monkeypatch.setattr(nodes, "llm", _FakeLLM(exc=RuntimeError("rate limit")))
    r = nodes._invoke_json("s", "u")
    assert isinstance(r, dict) and "error" in r


def test_invoke_json_coerces_non_dict(monkeypatch):
    # LLM이 dict 아닌 유효 JSON(리스트)을 반환해도 항상 dict로 강제돼야 한다.
    import agent_backend.agents.nodes as nodes
    monkeypatch.setattr(nodes, "llm", _FakeLLM(content="[1,2,3]"))
    r = nodes._invoke_json("s", "u")
    assert isinstance(r, dict) and "error" in r


def test_supervisor_survives_llm_failure(monkeypatch):
    # Supervisor는 모든 요청이 거치는 SPOF지만, 헬퍼가 실패를 흡수하므로 크래시
    # 없이 dict를 반환하고, route 키가 없어도 _route가 complex로 안전 처리한다.
    import agent_backend.agents.nodes as nodes
    monkeypatch.setattr(nodes, "llm", _FakeLLM(exc=RuntimeError("down")))
    result = node_supervisor({"question": "x"})
    assert isinstance(result["supervisor"], dict)
    assert _route(result) == "complex"


# ── graph.py _trust_gate() ───────────────────────────────────────────
def test_trust_gate_stops_on_low():
    assert _trust_gate({"analytics_engineer": {"trust_level": "LOW"}}) == "stop"


@pytest.mark.parametrize("trust", ["HIGH", "MEDIUM"])
def test_trust_gate_continues_on_ok(trust):
    assert _trust_gate({"analytics_engineer": {"trust_level": trust}}) == "continue"


def test_trust_gate_continues_when_missing():
    # trust_level 키가 없으면(헬퍼 실패 등) 안전하게 계속 진행 — 신뢰도 판정
    # 실패가 곧 전면 차단이 되지 않도록.
    assert _trust_gate({}) == "continue"


# ── graph.py _route() 방어 로직 ──────────────────────────────────────
def test_route_defaults_to_complex_when_missing():
    assert _route({}) == "complex"


def test_route_defaults_to_complex_on_unknown_value():
    assert _route({"supervisor": {"route": "이상한값"}}) == "complex"


@pytest.mark.parametrize("route", ["nonanalytic", "simple", "complex"])
def test_route_passes_through_valid_values(route):
    assert _route({"supervisor": {"route": route}}) == route
