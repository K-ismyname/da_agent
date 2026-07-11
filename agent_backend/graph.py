# LangGraph StateGraph 정의 — 에이전트 파이프라인 흐름
#
# [역할]
# agents/nodes.py의 8개 함수를 실제 그래프 노드로 등록하고, 노드 간 실행
# 순서(엣지)를 정의한다. 이 파일이 로드되면 즉시 컴파일된 pipeline 객체가
# 모듈 레벨에 생성되고(맨 아래), main.py가 이걸 그대로 import해서 쓴다.
#
# [왜 이렇게 설계했나]
# - 순서를 nodes.py 안에서 함수 호출 체인으로 직접 짜지 않고 별도 그래프
#   객체로 분리한 이유: LangGraph를 쓰면 조건부 분기(Gate)나 재시도, 병렬
#   실행 같은 제어 흐름을 선언적으로 표현할 수 있고, 그래프 시각화·상태
#   추적 같은 LangGraph 생태계 기능(체크포인트 등)도 그대로 활용 가능해진다.
from langgraph.graph import StateGraph, END
from agent_backend.state import AnalysisState
from agent_backend.agents.nodes import (
    node_supervisor, node_product_analyst, node_analytics_engineer,
    node_data_scientist, node_qa_reviewer, node_evaluator, node_head_of_data,
)


def _route(state: AnalysisState) -> str:
    """Supervisor가 정한 경로. 값이 없거나 이상하면 안전하게 complex(전체 체인)로."""
    r = state.get("supervisor", {}).get("route", "complex")
    return r if r in ("nonanalytic", "simple", "complex") else "complex"


def _supervisor_gate(state: AnalysisState) -> str:
    """Supervisor 직후 분기: 비분석→종료, 단순조회→Data Scientist로 직행,
    원인분석→기존 전체 체인(Planner부터)."""
    route = _route(state)
    if route == "nonanalytic":
        return "end"          # 에이전트 아무것도 안 돌리고 Supervisor 안내만 반환
    if route == "simple":
        return "data_scientist"  # Product Analyst/Analytics Engineer 등 사전 단계 스킵
    return "product_analyst"  # complex: Product Analyst부터 순차 체인


def _after_data_scientist(state: AnalysisState) -> str:
    """Data Scientist 직후 분기: 단순조회는 QA Reviewer(다중 결과 일관성 검증)를
    건너뛰고 바로 Evaluator(재조회 검증)로 — 단순 조회엔 대조할 여러 결과가 없기 때문."""
    return "simple" if _route(state) == "simple" else "complex"


def _trust_gate(state: AnalysisState) -> str:
    """Analytics Engineer가 데이터 신뢰도를 LOW로 판정하면 분석 진행을 중단한다.
    왜: 저품질/부족한 데이터로 Data Scientist가 분석을 강행하면 그럴듯하지만
    오도하는 결론이 나온다. "게이트키퍼"라는 이름값을 실제로 하게 만드는 지점 —
    QA/Eval FAIL과 같은 방식으로 실행 흐름을 막는다. trust_level 키가 없거나
    이상값이면(헬퍼 실패 등) 안전하게 계속 진행(HIGH 취급)해서, 신뢰도 판정
    실패가 곧 전면 차단이 되지는 않도록 한다."""
    trust = state.get("analytics_engineer", {}).get("trust_level", "HIGH")
    return "stop" if trust == "LOW" else "continue"


def _qa_gate(state: AnalysisState) -> str:
    """QA FAIL이면 파이프라인 종료, PASS/WARN이면 계속."""
    # 왜 여기서 멈추나: QA Reviewer가 이미 "숫자와 결론이 모순된다"고 판단했는데
    # 그 상태로 Head of Data까지 밀어붙이면 잘못된 결과를 사용자에게 그대로
    # 보여주게 된다. CLAUDE.md "QA Reviewer FAIL → 결과 출력 불가" 원칙의 실행 지점.
    verdict = state.get("qa_reviewer", {}).get("verdict", "FAIL")  # 키가 없으면 FAIL로 간주 — 안전 쪽으로 기본값 설정
    return "continue" if verdict in ("PASS", "WARN") else "stop"


def _eval_gate(state: AnalysisState) -> str:
    """Evaluation FAIL이면 종료, PASS/WARN이면 Head of Data로.
    (2026-07-09) BI Analyst 제거 — 대시보드는 /data(마트 직접 조회)로 이미
    그리고 있어 BI Analyst의 chart_data를 아무도 안 읽는 죽은 출력이었다."""
    verdict = state.get("evaluation", {}).get("verdict", "FAIL")
    return "continue" if verdict in ("PASS", "WARN") else "stop"


def build_graph():
    g = StateGraph(AnalysisState)  # 모든 노드가 공유할 상태 타입을 지정하며 그래프 생성

    g.add_node("run_supervisor", node_supervisor)
    g.add_node("run_product_analyst", node_product_analyst)
    g.add_node("run_analytics_engineer", node_analytics_engineer)
    g.add_node("run_data_scientist", node_data_scientist)
    g.add_node("run_qa_reviewer", node_qa_reviewer)
    g.add_node("run_evaluator", node_evaluator)
    g.add_node("run_head_of_data", node_head_of_data)

    g.set_entry_point("run_supervisor")  # 이제 항상 Supervisor에서 시작

    # Supervisor 분기 — 경로 자체를 3갈래로 나누는 지점
    g.add_conditional_edges("run_supervisor", _supervisor_gate, {
        "end": END,
        "data_scientist": "run_data_scientist",
        "product_analyst": "run_product_analyst",
    })

    # complex 경로: Product Analyst → Analytics Engineer → (신뢰도 게이트) → Data Scientist
    g.add_edge("run_product_analyst", "run_analytics_engineer")
    g.add_conditional_edges("run_analytics_engineer", _trust_gate, {
        "continue": "run_data_scientist",
        "stop": END,
    })

    # Data Scientist 직후: simple은 QA 스킵하고 Evaluator로, complex는 QA로
    g.add_conditional_edges("run_data_scientist", _after_data_scientist, {
        "simple": "run_evaluator",
        "complex": "run_qa_reviewer",
    })
    g.add_conditional_edges("run_qa_reviewer", _qa_gate, {
        "continue": "run_evaluator",
        "stop": END,
    })
    g.add_conditional_edges("run_evaluator", _eval_gate, {
        "continue": "run_head_of_data",
        "stop": END,
    })
    g.add_edge("run_head_of_data", END)

    return g.compile()  # compile() 이후에야 실행 가능한 그래프 객체가 됨 — 이전까지는 배선 정의일 뿐


# 모듈 로드 시점에 즉시 그래프를 빌드해 전역 pipeline 객체로 노출.
# main.py는 이 pipeline.invoke(...)만 호출하면 되고, 그래프 배선 자체는 몰라도 된다.
pipeline = build_graph()
