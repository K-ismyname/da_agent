# AI Data Team OS

GA4로 수집한 커뮤니티 웹사이트 데이터를 7개 AI 에이전트가 자동 분석해서 인사이트를 뽑아주는 멀티 에이전트 시스템.

## Architecture
```
Next.js (프론트 + API proxy)
    ↓ GET /analyze?q=
FastAPI + LangGraph (agent_backend/)
    ↓ tool calling
BigQuery (formula_silk_analytics)
```

## Tech Stack
- Data Source: Google Analytics 4 (GA4 `G-3T1X4Z1H28`)
- Warehouse: BigQuery (dataset: `formula_silk_analytics`)
- Agent Backend: Python FastAPI + LangGraph (`agent_backend/`)
- Frontend: Next.js + React + Tailwind + Chart.js (`dashboard/`)
- AI: OpenAI GPT-4o (tool calling 기반 진짜 멀티 에이전트)
- Deploy: Vercel (frontend) + 별도 Python 서버 (backend)

## Directory Structure
- agent_backend/      : Python FastAPI + LangGraph 에이전트 파이프라인
  - main.py           : FastAPI 진입점
  - graph.py          : LangGraph StateGraph 정의
  - state.py          : AnalysisState TypedDict
  - agents/nodes.py   : 7개 에이전트 노드 함수
  - tools/bigquery.py : BigQuery tool calling 함수
- dashboard/          : Next.js 프론트엔드 + API proxy
- knowledge/          : KPI Dictionary, Business Context (SSOT)
- skills/             : 17개 분석 스킬 정의
- agents/             : 에이전트 역할 정의 문서

## BigQuery Marts (READ ONLY)
Dataset: `formula_silk_analytics`
- dashboard_kpi         : core KPI metrics
- landing_page_mart     : landing page performance
- marketing_channel_mart: channel attribution
- funnel_mart           : engagement funnel
- journey_mart          : user journey paths
- cohort_mart           : cohort retention
- ab_test_mart          : Meta Ads × GA4 A/B test (joined via join_key, date × variant)

## Core Principles (MUST FOLLOW)
- Mart only: never query Raw events_* tables directly
- No SQL writing: agents must use Skills for analysis methods
- KPI SSOT: all KPI definitions from knowledge/kpi_dictionary.md only
- All results must pass QA Reviewer validation before output
- QA Reviewer FAIL → Head of Data cannot output results
- Dashboard renders API results only — AI does NOT generate data
- API responses must be structured JSON
- Agent는 SQL 미작성 · Skill은 방법만 · KPI는 Dictionary 단일 정의

## Absolute Don'ts
- DELETE, UPDATE, DROP queries forbidden
- Raw events_* table direct access forbidden
- Generating data not in marts forbidden
- Hardcoding KPI definitions in code forbidden
- Skills/agents files must be written in English (token efficiency)
- `.env.local` 수정 금지
- `credentials.json` 수정/노출 금지

## Agent Pipeline Order
Supervisor → Product Analyst → Analytics Engineer → Data Scientist → QA Reviewer → Evaluator → Head of Data

0. Supervisor — 질문 분류(nonanalytic/simple/complex), 라우팅 게이트
1. Product Analyst — 분석 방향 설정 (complex 경로만)
2. Analytics Engineer — Mart 데이터 신뢰도 검증 → trust_level (LOW 시 중단)
3. Data Scientist — 퍼널/코호트/채널/여정/A·B 테스트 분석 (tool-calling agent)
4. QA Reviewer — 결과 검증 (FAIL 시 중단)
5. Evaluator — Confidence/Hallucination Risk/Grounded 스코어링, 점수는 코드가 계산 (FAIL 시 중단)
6. Head of Data — Executive Brief 작성 (항상 실행)

경로: complex = 전체 체인 / simple = Supervisor → Data Scientist → Evaluator → Head of Data / nonanalytic = 조기 종료.
게이트 3개(trust LOW · QA FAIL · Eval FAIL)는 각각 통과 못 하면 422 반환.
Planner·BI Analyst 노드는 제거됨(스킬 선택은 노드별 고정, 대시보드 JSON은 각 노드 결과 그대로 사용).

## 추가 엔드포인트 (관측·능동 감시)
- `/insights` : run_log 기반 최근 분석 이력
- `/anomaly-check` : 지표 급락 감지 → 알림 (LLM 없이 SQL)
- `/instrumentation-check` : 배포됐는데 이벤트 미수집(계측 공백) 감시
- 매 /analyze 호출은 run_log에 기록됨

## Stop Hooks (분석 완료 시 자동 실행)
report.md 생성 → PDF 변환(fpdf2, 한글 폰트 자동탐색) → Slack 알림(SLACK_WEBHOOK_URL 설정 시) → 이메일 발송(GMAIL_ADDRESS/GMAIL_APP_PASSWORD/EMAIL_TO 설정 시, PDF 첨부)
자동화: `.github/workflows/`의 weekly-briefing(주간)·daily-checks(이상·계측 일일)가 배포된 백엔드를 cron으로 호출

## A/B Test Analysis (Meta Ads × GA4)
- 데이터: 자료/*.csv → `agent_backend/scripts/load_ab_test_mart.py`로 BigQuery 적재
- 지표 프레임: Primary(CVR·ROAS·CPP) + Guardrail(CPC·CPM·Cost/ATC) — 정의는 kpi_dictionary.md
- 통계 검정: `run_significance_test(experiment="ab_test")` 툴 (two-proportion z-test, LLM이 p-value 추정 금지)
- 대시보드: /ab-test 페이지

## Running the Project
```bash
npm install
npm run dev       # http://localhost:3000
```

## Cost Reference
~$0.27-0.29 USD per full analysis run (8 LLM calls, ~65k tokens, GPT-4o)
