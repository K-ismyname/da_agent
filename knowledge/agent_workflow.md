# Agent Workflow

## Overview
Sequential multi-agent pipeline that analyzes community website GA4 data and produces an executive brief.

**Trigger:** `GET /api/analyze?q=질문`
**Total LLM calls:** 7
**Model:** GPT-4o

---

## Pipeline

```
User Question
     │
     ▼
[1] Planner
     │ agents[], skills[], reason
     ▼
[2] Product Analyst
     │ hypothesis, focus_metrics, analysis_direction
     ▼
[3] Analytics Engineer          ← BigQuery Mart 데이터 병행 투입
     │ trust_level, issues, confidence
     ▼
[4] Data Scientist
     │ root_cause, funnel_insight, channel_insight, cohort_insight, evidence[]
     ▼
[5] QA Reviewer  (always runs)
     │ verdict: PASS|WARN|FAIL
     │
     ├── FAIL → 즉시 중단, 422 반환
     │
     └── PASS/WARN
          ▼
         [6] BI Analyst
              │ kpi_summary, chart_data
              ▼
         [7] Head of Data  (always runs)
              │ headline, insights[3], actions[3], confidence, qa_verdict
              ▼
           API JSON Response
```

---

## Agent Definitions

### 1. Planner
- **File:** `../agents/` (implicit)
- **Input:** user question (string)
- **Output:** `{ agents[], skills[], reason }`
- **Role:** Selects minimum required agents and skills based on the question
- **Rules:**
  - QA Reviewer and Head of Data always included regardless of selection
  - Must justify selection with `reason`

---

### 2. Product Analyst
- **File:** `../agents/product_analyst.md`
- **Input:** question + Planner output
- **Output:** `{ headline, focus_metrics[], hypothesis, analysis_direction, activity }`
- **Role:** Sets analysis direction and hypothesis before data is touched
- **Rules:**
  - North Star Metric = 가입 전환율
  - Funnel: 방문 → 아티클 열람 → 가입 클릭 → 가입 완료

---

### 3. Analytics Engineer
- **File:** `../agents/analytics_engineer.md`
- **Input:** BigQuery Mart data (all 6 tables)
- **Output:** `{ trust_level: HIGH|MEDIUM|LOW, issues[], confidence, activity }`
- **Role:** Validates data quality before analysis begins
- **Rules:**
  - If trust_level = LOW → Data Scientist must flag low confidence
  - Never queries Raw events_* tables

---

### 4. Data Scientist
- **File:** `../agents/data_scientist.md`
- **Skills used:** `funnel_analysis`, `cohort_analysis`, `marketing_channel_analysis`, `journey_analysis`
- **Input:** Mart data + Product Analyst direction
- **Output:** `{ root_cause, funnel_insight, channel_insight, cohort_insight, evidence[], activity }`
- **Role:** Finds root cause through multi-dimensional analysis
- **Rules:**
  - Evidence must reference specific numbers from data
  - No SQL writing — Mart queries only

---

### 5. QA Reviewer *(always runs)*
- **File:** `../agents/qa_reviewer.md`
- **Input:** Product Analyst + Analytics Engineer + Data Scientist outputs
- **Output:** `{ verdict: PASS|WARN|FAIL, issues[], confidence, activity }`
- **Role:** Cross-validates consistency across all agent outputs
- **Rules:**
  - FAIL → pipeline stops, 422 returned
  - WARN → pipeline continues with disclaimer
  - Cannot be skipped

---

### 6. BI Analyst
- **File:** `../agents/bi_analyst.md`
- **Input:** Mart data + QA Reviewer output
- **Output:** `{ kpi_summary, chart_data, activity }`
- **Role:** Structures validated data into dashboard-ready JSON
- **Rules:**
  - Only uses QA-validated numbers
  - Does not modify or reinterpret analysis results

---

### 7. Head of Data *(always runs)*
- **File:** `../agents/head_of_data.md`
- **Input:** All 6 agent outputs combined
- **Output:** `{ headline, insights[max 3], actions[max 3], confidence, qa_verdict, activity }`
- **Role:** Final executive brief — synthesis and decision
- **Rules:**
  - Max 3 insights, max 3 actions
  - Cannot override QA FAIL verdict
  - confidence < 40% → recommend re-run

---

## Data Flow

```
BigQuery Mart (formula_silk_analytics)
  dashboard_kpi
  funnel_mart
  marketing_channel_mart        ──► Analytics Engineer (Step 3)
  landing_page_mart                      │
  journey_mart                           │ (validated data)
  cohort_mart                            ▼
                                   Data Scientist (Step 4)
```

---

## Response Structure

```json
{
  "question": "사용자 질문",
  "source": "dummy | bigquery",
  "data": { "kpi": [], "funnel": [], "channel": [], "landing": [], "cohort": [] },
  "pipeline": {
    "planner": {},
    "productAnalyst": {},
    "analyticsEngineer": {},
    "dataScientist": {},
    "qaReviewer": {},
    "biAnalyst": {}
  },
  "brief": {
    "headline": "...",
    "insights": [],
    "actions": [],
    "confidence": 82,
    "qa_verdict": "PASS"
  }
}
```

---

## Skip Logic

| Agent | Skippable? | Condition |
|-------|-----------|-----------|
| Planner | No | Always runs |
| Product Analyst | No | Always runs |
| Analytics Engineer | No | Always runs |
| Data Scientist | Yes | If Planner excludes it |
| QA Reviewer | **No** | Always runs |
| BI Analyst | Yes | If Planner excludes it |
| Head of Data | **No** | Always runs |

---

## Cost Reference
~7 LLM calls per full run (GPT-4o)
Estimated: $0.10–0.15 USD per analysis
