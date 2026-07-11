# AI Data Team OS — 기술 개념 전면 정리

> GA4 데이터를 8개 AI 에이전트가 순차 분석해 인사이트를 만드는 멀티 에이전트 시스템.
> 이 문서는 실제 코드를 근거로 사용된 모든 기술의 개념을 정리한다.

---

## 0. 전체 데이터 흐름 (한눈에)

```
브라우저 (dashboard/app/page.tsx, React)
  │  ① 차트용: fetch('/api/data')          ← LLM 없이 마트 원시데이터
  │  ② 분석용: fetch('/api/analyze?q=...')  ← 8개 에이전트 파이프라인
  ▼
Next.js API Route (dashboard/app/api/*/route.ts)  ← 프록시
  │  backendFetch() 로 공유 시크릿 헤더 부착
  ▼
FastAPI (agent_backend/main.py)
  │  /analyze  → LangGraph 파이프라인 실행
  │  /data     → 마트 SELECT 결과 직접 반환
  │  /ab-test  → A/B 요약·일별추이 반환
  ▼
LangGraph StateGraph (agent_backend/graph.py)
  Planner → Product Analyst → Analytics Engineer → Data Scientist
         → QA Reviewer[게이트] → Evaluator[게이트] → BI Analyst → Head of Data
  │  각 노드가 GPT-4o 호출, 일부는 tool calling 으로
  ▼
BigQuery Marts (7개, READ ONLY)  ← formula_silk_analytics
  │
  ▼ (분석 완료 후 백그라운드)
Stop Hooks (agent_backend/hooks.py): report.md → PDF → Slack
```

---

## 1. 데이터 소스 — GA4 (Google Analytics 4)

웹사이트 방문자 행동(페이지뷰·클릭·전환 등)을 **이벤트 단위**로 기록하는 구글 분석 도구. 모든 행동이 `events_*` 원본 테이블에 시간순으로 쌓인다.

- 이 프로젝트의 원천 데이터.
- **원본 이벤트 테이블 직접 조회는 금지** — 구조가 복잡·대용량이라 에이전트가 실수하기 쉽다. 대신 미리 가공한 마트만 조회한다.

## 2. 데이터 웨어하우스 — BigQuery

구글의 **서버리스 대용량 분석 DB**. SQL로 조회하되 서버 관리 없이 대용량을 빠르게 집계한다.

- **마트(Mart)**: 원본을 미리 가공한 "바로 쓸 수 있는 요약 테이블". 7개 존재.
  - `dashboard_kpi`, `funnel_mart`, `marketing_channel_mart`, `landing_page_mart`, `journey_mart`, `cohort_mart`, `ab_test_mart`
- **VIEW 전환**(커밋 `0cffc29d`): 6개 마트를 실제 테이블이 아니라 VIEW로 전환. VIEW는 데이터를 복사·저장하지 않고 조회 시마다 정의된 SQL을 즉시 실행하는 가상 테이블 → 배치 스냅샷 대신 **항상 최신 데이터 실시간 반영**.
- **A/B 마트 적재**([load_ab_test_mart.py](agent_backend/scripts/load_ab_test_mart.py)): Meta Ads CSV(`meta_ads_src`)와 GA4(`ga4_landing_src`)를 `join_key`로 JOIN해 `CREATE OR REPLACE TABLE`로 생성. 이건 VIEW가 아니라 1회성 배치 적재.
- 리전: `asia-northeast3`(서울), 프로젝트: `gen-lang-client-0891732976`.

## 3. 에이전트 오케스트레이션 — LangGraph

여러 단계(노드)를 거치는 **상태 기계(state machine)**를 코드로 정의하는 라이브러리. [graph.py](agent_backend/graph.py) 기준.

- **StateGraph**: 파이프라인 뼈대. `add_node`로 단계 등록, `add_edge`로 "A→B" 흐름 연결.
- **State (`AnalysisState`)**: 각 노드가 값을 채워 넣는 공유 딕셔너리([state.py](agent_backend/state.py)). `TypedDict`로 정의. Planner가 채운 값을 다음 노드가 읽고 자기 결과를 덧붙이는 릴레이 구조. **각 노드는 `{"키": 결과}` 딕셔너리만 반환** → LangGraph가 전체 상태에 병합.
- **조건부 엣지(`add_conditional_edges`)**: 상태 값을 보고 다음 단계로 갈지 멈출지(`END`) 결정.
  - `_qa_gate`: QA verdict가 FAIL이면 파이프라인 중단.
  - `_eval_gate`: Evaluation verdict가 FAIL이면 중단.
  - → CLAUDE.md의 "QA FAIL → 결과 출력 불가" 원칙의 실체.

## 4. LLM 활용 — OpenAI GPT-4o + Tool Calling

`ChatOpenAI(model="gpt-4o", temperature=0)`. temperature=0은 매번 같은 입력에 최대한 일관된(결정적) 출력을 내라는 뜻.

### 두 가지 LLM 호출 패턴 ([nodes.py](agent_backend/agents/nodes.py))
- **`_invoke_json`**: 툴 없이 프롬프트만 주고 JSON 응답을 바로 받음. Planner·Product Analyst·QA·BI·Head of Data가 사용.
- **`_invoke_with_tools`**: **Tool calling 루프**. LLM에게 도구 목록을 주면(`bind_tools`), LLM이 "어떤 함수를 어떤 인자로 부를지" 스스로 결정 → 결과를 받아 다시 판단 → 최종 JSON을 낼 때까지 반복.
  - `MAX_TOOL_ROUNDS = 10`: 무한 루프·비용 폭주 방지 상한. 마지막 라운드엔 툴을 떼고 강제로 답변만 받음.
  - 툴 실패는 크래시 대신 `"TOOL ERROR: ..."` 문자열로 반환 → 에이전트가 읽고 재시도(에러 복원력).
  - Analytics Engineer·Data Scientist·Evaluator가 사용(BigQuery 조회 필요).

### BigQuery 툴 ([tools/bigquery.py](agent_backend/tools/bigquery.py))
`@tool` 데코레이터로 LangChain 툴 등록. 4개:
- `query_mart(table)`: 마트 SELECT (화이트리스트 검증 — 허용된 7개만).
- `get_date_range(table)`: 마트 날짜 범위. 날짜 컬럼 없는 마트는 "스냅샷"으로 안내.
- `get_ab_test_summary`: variant별 집계 지표(CVR·ROAS·CPC 등)를 `SAFE_DIVIDE`로 계산.
- `run_ab_significance_test`: **Python으로 결정적 계산**하는 two-proportion z-test.

### 핵심 안전장치 — SSOT 주입
- **`knowledge/kpi_dictionary.md`, `business_context.md`를 프롬프트에 그대로 삽입** → LLM이 지표를 임의로 재정의 못 함.
- **Planner가 고른 skill 문서(`skills/*/*.md`)를 프롬프트에 병합** (`_skill_context`) → LLM이 SQL을 새로 짜는 게 아니라 문서에 적힌 분석 방법론을 따르게 함.
- → CLAUDE.md의 "Agent는 SQL 미작성 · Skill은 방법만 · KPI는 Dictionary 단일 정의" 원칙의 실체.

## 5. 통계 검정 — Two-proportion Z-test

A/B 두 그룹의 전환율(비율) 차이가 우연인지 통계적으로 유의한지 판정.

- `run_ab_significance_test`가 `math.erfc`로 **Python에서 직접 p-value 계산** → LLM이 p-value를 "추정"해 환각 내는 것을 원천 차단.
- variant가 2개가 아니거나 세션이 0이면 에러 문자열 반환(크래시 방지, 커밋 `1393` 참고).
- 프레임: **Primary**(CVR·ROAS·Cost per Purchase)로 GO/NO-GO 판단 + **Guardrail**(CPC·CPM·Cost/ATC) 악화 감시.

## 6. 자체 평가 — Evaluator (LLM-as-judge + 결정적 스코어링)

CLAUDE.md엔 "Evaluator" 한 줄이지만 실제로는 2단계 하이브리드 ([nodes.py](agent_backend/agents/nodes.py) `node_evaluator`):

1. **`_judge_claims`** (LLM judge): 마트를 재조회해 Data Scientist의 **모든 수치 주장**을 실제 데이터와 대조(±2% 허용). 수치는 PASS/PARTIAL/FAIL, 서술은 YES/PARTIAL/NO로 판정만 하고 점수는 안 냄.
2. **결정적 스코어링** (순수 Python): judge 결과를 집계해 **Confidence / Hallucination Risk / Grounded(Numeric·LLM) / Verdict**를 계산. LLM 출력 키가 빠져도 `.get()` 기본값으로 크래시 안 함.
   - Confidence ≥70 & Halluc.Risk ≤30 → PASS / ≥50 & ≤50 → WARN / 그 외 FAIL.

## 7. 백엔드 API — FastAPI

Python REST API 프레임워크. 타입힌트 기반 검증·비동기(async) 지원. [main.py](agent_backend/main.py).

- 엔드포인트: `/analyze`(파이프라인), `/data`(차트용 마트 직접 조회), `/ab-test`, `/health`.
- **공유 시크릿 미들웨어**: `x-backend-secret` 헤더 검증 → Next.js 프록시만 호출하도록 제한(미설정 시 로컬 개발용으로 스킵).
- **전역 예외 핸들러**: 미처리 예외를 500 JSON으로 변환해 프론트에 원인 전달.
- `BackgroundTasks`: 응답을 먼저 돌려주고 Stop Hooks를 백그라운드에서 실행.
- `uvicorn`: FastAPI를 실제로 구동하는 ASGI 서버. `python-dotenv`: `.env` 환경변수 로드. `pyarrow`: BigQuery↔pandas 컬럼 포맷.

## 8. 프론트엔드 — Next.js + React + Tailwind

- **Next.js**(16.2.9): React 기반 프레임워크. 여기선 대시보드 렌더링 + **API 프록시**(브라우저 요청을 FastAPI로 중계) 역할. ⚠️ `dashboard/AGENTS.md`에 "이 버전은 브레이킹 체인지가 있으니 `node_modules/next/dist/docs/`를 확인하라"는 경고.
- **React**(19.2.4): 컴포넌트 단위 UI. `page.tsx`는 `useState`/`useEffect`로 상태 관리 — 차트 데이터(30초 타임아웃)와 분석 브리프(180초 타임아웃)를 각각 병렬 fetch.
- **Tailwind CSS**(v4): 유틸리티 클래스 기반 스타일링.
- **결과 렌더링은 HTML `<table>`** — 뒤의 "문서-코드 불일치" 참고.
- `@google-cloud/bigquery`(JS SDK)가 프론트에도 있으나, 현재 `/data`·`/ab-test`는 FastAPI 경유로 통일됨(`route.ts`가 `backendFetch` 사용). JS SDK는 과거 잔재/미사용에 가까움.

## 9. 리포트 & 알림 — Stop Hooks

분석 완료(Event) → 후속 액션(Action) 체인 ([hooks.py](agent_backend/hooks.py)). `config/workflows.yaml`의 `hooks.Stop` 정의를 구현.

- **report**: 브리프·A/B·평가점수를 `executive_report.md`로 생성.
- **PDF**(`fpdf2`): 마크다운 → PDF. **한글 폰트 자동 탐색** — 존재만으론 부족(AppleGothic은 OS/2 테이블 문제로 실패)해서 `FPDF().add_font()`로 실제 로드 가능한 폰트만 채택. 실패해도 파이프라인은 계속.
- **Slack**(`urllib`): `SLACK_WEBHOOK_URL` 설정 시에만 Webhook POST로 알림. (외부 의존성 없이 표준 라이브러리로 구현)

## 10. 지식·스킬 문서 체계 (SSOT의 실체)

- **`knowledge/`** (5개): `kpi_dictionary.md`(KPI 단일 정의), `business_context.md`, `data_model.md`, `metric_definition.md`, `agent_workflow.md`. 지표를 코드에 하드코딩하지 않고 이 문서만 참조하게 강제.
- **`skills/`** (17개, 5카테고리): `planning`·`data_foundation`·`analytics`·`validation`·`delivery`. 각 스킬은 Goal·Input Mart·Analysis Steps·Expected Output·QA Checklist를 담은 마크다운. LLM이 실행 시 프롬프트로 주입받아 따름.
- **`config/workflows.yaml`**: 마트·스킬·에이전트 배정·실행 순서·Planner 규칙·Hooks를 한 파일에 선언한 설정 SSOT.

## 11. 테스트 — pytest

`agent_backend/tests/test_pure_logic.py`. **LLM 호출 없이** 검증 가능한 순수 로직만 테스트: `_extract_json`의 여러 입력 형태 파싱, Evaluator 스코어링. `monkeypatch`로 LLM judge를 가짜로 대체해 결정적 스코어링만 검증.

## 12. 배포

- 프론트(Next.js): **Vercel**. `maxDuration=300`으로 함수 타임아웃 연장(LLM 파이프라인이 2~3분).
- 백엔드(FastAPI): 별도 Python 서버(기록상 Railway → Hugging Face Spaces 이전 이력).

---

## ⚠️ 발견한 문서-코드 불일치 (정리 중 확인)

| 항목 | 문서(CLAUDE.md/yaml) | 실제 코드 | 비고 |
|---|---|---|---|
| **LLM 모델** | `workflows.yaml`: `claude-sonnet-4-6` / CLAUDE.md: GPT-4o | **GPT-4o** (`nodes.py` 하드코딩) | yaml의 model 설정은 미사용. 코드가 진실. |
| **차트 라이브러리** | CLAUDE.md: Chart.js | **HTML `<table>`** (`page.tsx`) | Chart.js 의존성 없음. 계획만 남고 미구현. |
| **에이전트 수** | "7개 노드" (CLAUDE.md) | **8개 노드** | Evaluator 포함 시 8개. |
| **마트 개수** | "8개 AI 에이전트가 6개 마트" 등 혼재 | 마트 **7개** | `dashboard_kpi`~`ab_test_mart`. |

> 이런 불일치는 문서가 계획 시점에 쓰이고 코드가 이후 진화하며 생긴 것. **판단 기준은 항상 실제 코드**.

---

## 한 문장 요약

사용자가 대시보드에 질문 입력 → Next.js가 FastAPI로 프록시 → FastAPI가 LangGraph 파이프라인 실행 → 8개 에이전트가 GPT-4o의 tool calling으로 BigQuery 마트를 순차 조회·검증하되, KPI/Skill 문서(SSOT)를 프롬프트에 주입받아 지표 재정의·SQL 작성·p-value 추정을 원천 차단 → QA/Evaluator 게이트를 통과한 결과만 JSON으로 반환해 표로 렌더링하고, 동시에 PDF·Slack으로 리포트 발행.
