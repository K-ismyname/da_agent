# LangGraph 파이프라인 전체 상태 정의
#
# [역할]
# 에이전트 노드(supervisor ~ head_of_data)가 서로 주고받는 "공유 상태"의 타입.
# LangGraph의 모든 노드는 이 하나의 dict를 입력받고, 자기 결과만 채워서 반환한다.
# LangGraph가 노드의 반환값을 이 State에 병합(merge)해가며 파이프라인을 진행시킨다.
#
# [왜 이렇게 설계했나]
# - 노드마다 별도 인자/리턴 타입을 쓰지 않고 하나의 State를 공유하는 이유는
#   LangGraph의 StateGraph 자체가 "공유 상태 + 노드 함수" 모델로 동작하기 때문.
#   각 노드가 이전 노드들의 결과(state["product_analyst"] 등)를 자유롭게 참조할 수 있어야
#   Data Scientist가 Product Analyst의 방향성을 참고하는 식의 파이프라인이 가능해진다.
# - 값 타입을 전부 dict(Any 수준)로 둔 이유는, 각 에이전트의 출력 스키마가
#   LLM 프롬프트 안에서 자유형식 JSON으로 정의되기 때문(agents/nodes.py 참고).
#   너무 엄격한 타입을 걸면 LLM 출력 스키마가 바뀔 때마다 여기도 고쳐야 해서
#   유연성을 우선했다(대신 안전성은 nodes.py의 방어적 파싱이 담당).
from typing import TypedDict, Any

class AnalysisState(TypedDict):
    question: str          # 사용자의 원본 질문 — 파이프라인의 시작점, 모든 노드가 참조 가능
    supervisor: dict        # Supervisor 결과: route(nonanalytic/simple/complex) + 비분석 시 안내 message
    product_analyst: dict   # Product Analyst 결과: 분석 방향, 가설
    analytics_engineer: dict  # Analytics Engineer 결과: 데이터 신뢰도 검증
    data_scientist: dict    # Data Scientist 결과: 실제 분석 인사이트 (퍼널/코호트/A·B 등)
    qa_reviewer: dict       # QA Reviewer 결과: 앞 결과들의 일관성 검증 verdict
    evaluation: dict        # Evaluator 결과: Confidence/Hallucination Risk 점수
    head_of_data: dict      # Head of Data 결과: 최종 Executive Brief
    error: str | None       # 파이프라인 어디서든 에러 발생 시 채워지는 필드 (현재 미사용 — 훅으로 남겨둠)
