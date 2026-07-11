# AI Data Team OS — Architecture

## Data Flow
```
GA4 (G-3T1X4Z1H28)
 └─ 자동 Export (일 1회)
BigQuery Raw: analytics_543337410.events_*          ← 에이전트 직접 접근 금지
 └─ scripts/build_marts.py 등 (Mart 생성 SQL만 Raw 접근 허용)
BigQuery Mart: formula_silk_analytics               ← 에이전트는 여기만 조회
     ├── dashboard_kpi                (VIEW)
     ├── funnel_mart                  (VIEW)
     ├── marketing_channel_mart       (VIEW)
     ├── landing_page_mart            (VIEW)
     ├── journey_mart                 (VIEW)
     ├── cohort_mart                  (VIEW)
     ├── search_query_mart            (VIEW, url_decode UDF)
     ├── recommendation_mart          (VIEW)
     ├── signup_prompt_experiment_mart(VIEW)
     ├── home_sort_experiment_mart    (VIEW)
     └── ab_test_mart                 (TABLE, 정적 CSV 적재분 — 스터디 실습 데이터)

── Next.js (Vercel) ──────────────────────────────────────────────┐
│  app/api/analyze/route.ts  → x-backend-secret 헤더 부착 프록시   │
└──────────────────────────────────────────────────────────────────┘
 ▼ GET /analyze?q=
── FastAPI (Railway, 상시 실행) — agent_backend/ ──────────────────┐
│  knowledge/kpi_dictionary + business_context → 프롬프트 런타임    │
│  주입 (SSOT, 코드에 지표 하드코딩 금지)                            │
│                                                                    │
│  LangGraph StateGraph (graph.py) — 공유 AnalysisState(state.py)   │
│                                                                    │
│  Supervisor ─(route)─┬─ nonanalytic → 조기 종료                   │
│                      ├─ simple  → Data Scientist → Evaluator      │
│                      │            → Head of Data                   │
│                      └─ complex → 전체 체인 ↓                      │
│     Product Analyst → Analytics Engineer ─[trust LOW? 422]─       │
│     → Data Scientist → QA Reviewer ─[FAIL? 422]─                  │
│     → Evaluator ─[FAIL? 422]─ → Head of Data                      │
│                                                                    │
│  · Analytics Engineer / Data Scientist / Evaluator = tool-calling │
│    에이전트 (BigQuery 조회를 스스로 반복 호출)                     │
│  · Confidence·Hallucination Risk 점수는 코드가 계산(LLM 아님)     │
│  · A/B 유의성 검정(two-proportion z-test)도 Python 결정론 계산    │
│  · Stop Hook(hooks.py): report.md → PDF → Slack → Email(PDF 첨부) │
└──────────────────────────────────────────────────────────────────┘
 ▼
JSON { supervisor · product_analyst · analytics_engineer · data_scientist
       · qa_reviewer · evaluation · head_of_data }
 ▼
Dashboard (dashboard/app — React/Tailwind/Chart.js) ← API JSON만 렌더

## 능동 감시·자동화 엔드포인트 (LLM 파이프라인과 별개)
/anomaly-check          지표 급락 감지 → 알림 (SQL만, LLM 없음)
/instrumentation-check  배포됐는데 이벤트 미수집(계측 공백) 감시
/insights               run_log 기반 최근 분석 이력
.github/workflows/weekly-briefing.yml  주간 /analyze cron
.github/workflows/daily-checks.yml     일일 anomaly·instrumentation cron

## Core Principles (all layers)
- Mart only · Raw events_* 직접 접근은 마트 생성 SQL에서만
- 에이전트는 SQL 미작성 · Skill은 방법만 · KPI는 Dictionary SSOT
- 판단은 AI, 계산·검증은 코드 (점수·통계 검정은 Python)
- Dashboard는 API 결과만 렌더 · AI가 데이터를 생성하지 않음
- 3중 게이트(trust LOW · QA FAIL · Eval FAIL) 통과분만 출력
```

## Key Files
```
agent_backend/main.py            ← FastAPI 진입점 + BACKEND_SHARED_SECRET 미들웨어
                                   엔드포인트: /analyze /data /ab-test
                                   /anomaly-check /instrumentation-check /insights /health
agent_backend/graph.py           ← LangGraph StateGraph + 라우팅/게이트 함수
                                   (_supervisor_gate, _trust_gate, _qa_gate, _eval_gate)
agent_backend/state.py           ← AnalysisState TypedDict (공유 상태)
agent_backend/agents/nodes.py    ← 7개 노드 함수 + 헬퍼(_invoke_json, _invoke_with_tools)
                                   knowledge/·skills/ 런타임 로드
agent_backend/tools/bigquery.py  ← query_mart, get_experiment_summary,
                                   run_significance_test, EXPERIMENT_METRICS 등
agent_backend/hooks.py           ← Stop Hook: report → PDF → Slack → Email
agent_backend/scripts/
  build_marts.py                     ← GA4 → Mart VIEW 생성
  build_signup_prompt_experiment_mart.py / build_home_sort_experiment_mart.py
  build_run_log_table.py             ← 분석 이력 로그 테이블
  load_ab_test_mart.py               ← Meta CSV × GA4 CSV → ab_test_mart TABLE
agent_backend/tests/test_pure_logic.py ← LLM 없는 순수 로직 단위 테스트

knowledge/kpi_dictionary.md      ← SSOT: 모든 KPI 정의
knowledge/business_context.md    ← 사이트 구조·지표→mart 매핑·실험 목록
knowledge/data_model.md          ← mart 관계·조인 키
knowledge/ab_test_framework.md   ← A/B 지표 프레임(Primary/Guardrail)
knowledge/metric_definition.md   ← 지표 Purpose·Grain·Refresh
knowledge/agent_workflow.md      ← 파이프라인 실행 순서 문서
skills/                          ← 재사용 분석 스킬 (analytics/*가 실제 주입됨)
agents/                          ← 에이전트 역할 정의 문서

dashboard/app/api/analyze/route.ts  ← 메인 분석 프록시 (maxDuration 300)
dashboard/app/api/data/route.ts     ← mart 데이터 fetch
dashboard/app/api/ab-test/route.ts  ← A/B 실험 페이지 데이터
dashboard/lib/backend.ts            ← 공유 시크릿 헤더 부착 fetch 헬퍼
```
