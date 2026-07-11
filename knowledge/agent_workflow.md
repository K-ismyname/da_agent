# Agent Workflow

## Overview
Supervisor가 질문을 3경로로 분류하는 멀티 에이전트 파이프라인. 커뮤니티 웹사이트
GA4 데이터를 분석해 검증된 Executive Brief를 만든다.

**Trigger:** `GET /analyze?q=질문` (Next.js `/api/analyze` 프록시 경유)
**Model:** GPT-4o (temperature=0)
**노드:** 7개 (Planner·BI Analyst는 제거됨)
**게이트:** 3개 — 하나라도 걸리면 422 반환 (trust LOW · QA FAIL · Eval FAIL)

> SSOT는 코드다: 흐름은 `agent_backend/graph.py`, 노드 로직은 `agents/nodes.py`.
> 이 문서는 그 구조의 설명이며, 불일치 시 코드가 이긴다.

---

## Pipeline (3 routes)

```
User Question
     ▼
[0] Supervisor  ── route 분류 ──┬─ nonanalytic → 안내 메시지만 반환 (에이전트 미실행)
                                ├─ simple  → [3] Data Scientist → [5] Evaluator → [6] Head of Data
                                └─ complex → 전체 체인 ↓
[1] Product Analyst
     ▼
[2] Analytics Engineer ──[trust_level == LOW? → 422 STOP]
     ▼
[3] Data Scientist  (A/B 질문이면 실험 전용 분기)
     ▼
[4] QA Reviewer ───────[verdict == FAIL? → 422 STOP]
     ▼
[5] Evaluator ─────────[verdict == FAIL? → 422 STOP]   (점수는 코드가 계산)
     ▼
[6] Head of Data  →  API JSON Response
```

- **simple 경로**는 Product Analyst·Analytics Engineer·QA Reviewer를 건너뛴다
  (단일 사실 조회엔 사전 방향 설정·다중 결과 대조가 불필요).
- **tool-calling 에이전트**(BigQuery를 스스로 반복 조회)는 Analytics Engineer·
  Data Scientist·Evaluator 3개. 나머지는 단발 LLM 호출.

---

## Node Definitions

### 0. Supervisor
- **Output:** `{ route: nonanalytic|simple|complex, reason, message }`
- **Role:** 경로 분기 게이트. "이탈률" 같이 여러 마트로 해석 가능한 지표는 complex로.
- **Gate:** nonanalytic이면 에이전트 미실행, 안내 message만 반환.

### 1. Product Analyst (complex only)
- **Output:** `{ headline, focus_metrics[], hypothesis, analysis_direction }`
- **Role:** 데이터 조회 전, business_context 기반으로 분석 방향·가설 설정.

### 2. Analytics Engineer (tool-calling)
- **Tools:** `query_mart`, `get_date_range`
- **Output:** `{ trust_level: HIGH|MEDIUM|LOW, tables_queried[], issues[{problem,fix}], confidence }`
- **Role:** 데이터 신뢰도 게이트키퍼. 표본 크기·결측·이상치 점검.
- **Gate:** `trust_level == LOW` → 파이프라인 중단(422).

### 3. Data Scientist (tool-calling)
- **Tools(일반):** `query_mart`, `get_date_range`
- **Tools(A/B):** + `get_experiment_summary`, `run_significance_test`
- **Skills:** 일반 분기는 `GENERAL_ANALYSIS_SKILLS`(funnel/cohort/journey/channel) 자동 주입,
  A/B 분기는 `ab_test_analysis` + `ab_test_framework.md` 주입.
- **Output(일반):** `{ answerable, root_cause, insights{...}, evidence[] }`
- **Output(A/B):** `{ experiment_match, experiment, primary_metrics[], significance, guardrail_metrics[], recommended_variant, ... }`
- **Role:** 실제 인사이트 생성. answerable=false면 "물어본 데이터가 없다"고 명시.

### 4. QA Reviewer (complex only)
- **Output:** `{ verdict: PASS|WARN|FAIL, issues[], confidence }`
- **Role:** 도구 없이, 앞 결과들의 논리적 일관성만 검증(숫자 재조회는 Evaluator 몫).
- **Gate:** `verdict == FAIL` → 중단(422).

### 5. Evaluator (tool-calling judge + 코드 집계)
- **Tools:** `query_mart`, `get_experiment_summary`, `run_significance_test`, `get_date_range`
- **Output:** `{ confidence, hallucination_risk, grounded_numeric, grounded_llm, verdict, checks{} }`
- **Role:** LLM이 개별 주장을 PASS/PARTIAL/FAIL 판정 → **점수는 Python이 결정론적으로 계산**.
- **Gate:** `verdict == FAIL` → 중단(422).

### 6. Head of Data
- **Output:** `{ headline, insights[≤3], actions[≤3] }` + confidence/qa_verdict는 코드가 덮어씀
- **Role:** 최종 Executive Brief(한국어). confidence·qa_verdict는 LLM 환각 방지를 위해
  Evaluator/QA의 실제 값으로 교체.

---

## Response Structure (SUCCESS)

```json
{
  "question": "사용자 질문",
  "route": "complex",
  "source": "bigquery",
  "pipeline": {
    "productAnalyst": {}, "analyticsEngineer": {},
    "dataScientist": {}, "qaReviewer": {}, "evaluation": {}
  },
  "brief": { "headline": "...", "insights": [], "actions": [], "confidence": 82, "qa_verdict": "PASS" },
  "hooks": "scheduled"
}
```
게이트에서 막히면 대신 422 + `{ error: "DATA_TRUST_LOW"|"QA_FAIL"|"EVAL_FAIL", ... }`.
nonanalytic이면 200 + `{ route: "nonanalytic", message }`.

---

## Skip Logic (경로별)

| Node | complex | simple | nonanalytic |
|------|:---:|:---:|:---:|
| Supervisor | ✓ | ✓ | ✓ |
| Product Analyst | ✓ | — | — |
| Analytics Engineer | ✓ | — | — |
| Data Scientist | ✓ | ✓ | — |
| QA Reviewer | ✓ | — | — |
| Evaluator | ✓ | ✓ | — |
| Head of Data | ✓ | ✓ | — |

---

## Cost Reference
complex 1회 ~$0.27–0.29 USD (GPT-4o, tool-calling 포함 ~65k tokens).
분석 완료 후 Stop Hook: report.md → PDF → Slack → Email (각각 환경변수 설정 시).
