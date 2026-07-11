# Skills — 런타임 주입 vs 참고용

각 스킬은 분석 절차·QA 체크리스트·anti-pattern을 담은 방법론 문서다. 코드는
`skills/*/*.md`를 전부 `SKILLS` dict로 로드하지만, **실제로 에이전트 프롬프트에
주입되는 것은 `analytics/` 5개뿐**이다. 나머지는 설계 참고용으로 유지한다.

## 런타임 주입되는 스킬 (5개)
`agent_backend/agents/nodes.py`가 Data Scientist 프롬프트에 직접 주입한다.

| 스킬 | 주입 지점 |
|---|---|
| `analytics/funnel_analysis` | Data Scientist 일반 분기 (`GENERAL_ANALYSIS_SKILLS`) |
| `analytics/cohort_analysis` | 〃 |
| `analytics/journey_analysis` | 〃 |
| `analytics/marketing_channel_analysis` | 〃 |
| `analytics/ab_test_analysis` | Data Scientist A/B 분기 |

## 참고용 스킬 (주입 안 됨)
`data_foundation/` · `delivery/` · `planning/` · `validation/`

이 문서들이 정의한 절차는 **코드로 이미 구현**되어 있어 프롬프트 주입이 불필요하다.
- `validation/qa_review`·`evaluation_scoring` → QA Reviewer·Evaluator 노드 로직
- `data_foundation/mart_validation`·`metric_validation` → Analytics Engineer 신뢰도 검증
- `delivery/report_writer`·`executive_summary` → Head of Data + `hooks.py` 리포트 생성

즉 방법론 문서(참고)와 실행 코드(실제)가 분리돼 있고, 주입되는 5개만 "LLM이 매번
읽어야 하는" 절차다. 나머지는 설계 의도·리뷰용으로 남긴다.
