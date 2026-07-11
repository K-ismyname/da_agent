# 데이터 분석 멀티 에이전트

> **"데이터 팀 없이도 데이터 팀처럼 분석한다"**

**Live**: [dashboard-leegahees-projects.vercel.app](https://dashboard-leegahees-projects.vercel.app) · Backend: [da-agent-backend-production-99f0.up.railway.app](https://da-agent-backend-production-99f0.up.railway.app)

---

## 프로젝트 소개

GA4로 수집한 웹사이트 데이터를 7개 AI 에이전트가 협업해 자동 분석하는 **데이터 분석 멀티 에이전트 프로젝트**입니다.

질문 하나를 입력하면 에이전트들이 역할을 나눠 BigQuery를 직접 조회하고, QA 검증과 환각 탐지를 거친 결과만 최종 리포트로 출력합니다.

### 왜 만들었나

전통적인 데이터 분석은 이런 흐름입니다.

```
질문 → SQL 작성 → 데이터 추출 → 분석 → 검증 → 시각화 → 리포트 작성
```

소규모 팀에서는 이 모든 역할을 한 명이 맡아야 합니다. 이 시스템은 그 흐름 전체를 에이전트로 대체합니다.

```
질문 한 줄 → [7 Agent Pipeline] → 검증된 Executive Brief
```

각 에이전트는 실제 데이터 팀의 역할 분담을 그대로 반영합니다. Supervisor가 질문을 분류해 경로를 정하고, Analytics Engineer가 데이터 신뢰도를 검증하고, Data Scientist가 분석하고, QA Reviewer와 Evaluator가 이중 검증한 뒤, Head of Data가 경영진 브리핑을 작성합니다.

### 핵심 설계 원칙

- **환각 방지**: 에이전트가 숫자를 추정하지 않습니다. 모든 수치는 BigQuery Mart에서 tool calling으로 직접 조회합니다.
- **3중 게이트**: Analytics Engineer의 신뢰도 LOW, QA Reviewer FAIL, Evaluator FAIL 중 하나라도 걸리면 결과를 출력하지 않고 422를 반환합니다.
- **판단은 AI, 계산·검증은 코드**: Confidence·Hallucination Risk 점수는 LLM이 아니라 Python이 계산하고, A/B 유의성 검정(z-test)도 코드가 결정론적으로 처리합니다.
- **KPI SSOT**: 모든 지표 정의는 `knowledge/kpi_dictionary.md` 하나에서만 관리합니다. 에이전트 프롬프트가 런타임에 이 문서를 직접 읽어 주입하므로, 코드에 지표를 하드코딩할 수 없습니다.
- **Skill 기반 분석 절차**: `skills/*.md`에 정의된 분석 단계·QA 체크리스트·anti-pattern을 각 노드 프롬프트에 런타임 주입합니다.

### 분석 가능한 질문 예시

```
이번 달 주요 지표와 이탈 원인을 분석해줘
퍼널에서 가장 많이 이탈하는 구간이 어디야?
가입 유도 실험(A/B)에서 어느 쪽 전환율이 더 높아?
신규 유저 코호트 리텐션이 어떻게 되고 있어?
```

---

## Architecture

```
Next.js (Vercel) — 프론트 + API Proxy
    ↓ GET /api/analyze?q=  (x-backend-secret 헤더 부착)
FastAPI (Railway, 상시 실행) — agent_backend/
    ↓ LangGraph StateGraph
7 Agent Pipeline (LangGraph)
    ↓ tool calling
BigQuery Mart (formula_silk_analytics) — GA4 기반 VIEW + 실험/정적 TABLE
    ↑ 쿼리 시점 즉시 재계산 (실시간)
GA4 Export (analytics_543337410.events_*)
```

## Agent Pipeline

```
Supervisor          ← 질문 분류(nonanalytic/simple/complex) + 라우팅 게이트
  ↓  (complex 경로)
Product Analyst
  ↓
Analytics Engineer  ← BigQuery 툴 사용, 신뢰도 LOW 시 422 후 종료
  ↓
Data Scientist      ← BigQuery 툴 사용 (퍼널/코호트/채널/여정/A·B 분석)
  ↓
QA Reviewer         ← FAIL 시 422 반환 후 종료
  ↓
Evaluator           ← Confidence / Hallucination Risk 스코어링(코드 계산), FAIL 시 종료
  ↓
Head of Data        ← Executive Brief (한국어)
```

simple 경로: Supervisor → Data Scientist → Evaluator → Head of Data (중간 검증 생략)

분석 완료 후 자동 실행: `report.md` → `PDF 변환` → `Slack 알림` → `이메일 발송(PDF 첨부)` (Stop Hooks, 각각 환경변수 설정 시)
능동 감시: `/anomaly-check`(지표 급락)·`/instrumentation-check`(계측 공백)를 GitHub Actions cron이 매일 호출

## Tech Stack

| Layer | Stack |
|---|---|
| Frontend | Next.js · React · Tailwind · Chart.js |
| API Proxy | Next.js API Routes |
| Agent Backend | Python FastAPI · LangGraph |
| AI | OpenAI GPT-4o (tool calling) |
| Data Warehouse | Google BigQuery |
| Data Source | Google Analytics 4 (GA4) |
| Deploy | Vercel (frontend) + Railway (backend, 상시 실행) |

## BigQuery Mart Tables

Dataset: `formula_silk_analytics` (READ ONLY)

| 테이블 | 설명 | 타입 |
|---|---|---|
| `dashboard_kpi` | 일별 핵심 KPI (사용자·세션·이탈율 등) | VIEW (실시간) |
| `funnel_mart` | 커뮤니티 5단계 전환 퍼널 | VIEW (실시간) |
| `marketing_channel_mart` | 채널별 세션·참여 현황 | VIEW (실시간) |
| `landing_page_mart` | 페이지별 뷰·스크롤·체류 시간 | VIEW (실시간) |
| `journey_mart` | 세션 내 페이지 이동 경로 | VIEW (실시간) |
| `cohort_mart` | 주차별 코호트 리텐션 | VIEW (실시간) |
| `search_query_mart` | 사이트 검색어·결과 없는 검색(콘텐츠 갭) | VIEW (실시간) |
| `recommendation_mart` | 해시태그 기반 관련 글 추천 노출·클릭 | VIEW (실시간) |
| `signup_prompt_experiment_mart` | 가입 유도 A/B 실험 (variant × date) | VIEW (실시간) |
| `home_sort_experiment_mart` | 홈 정렬 방식 A/B 실험 (variant × date) | VIEW (실시간) |
| `ab_test_mart` | Meta Ads × GA4 A/B 데이터 (⚠️ 스터디 실습 데이터셋 — 실제 집행 데이터 아님) | TABLE (정적 CSV 적재분) |

GA4 기반 마트는 `CREATE OR REPLACE VIEW`로 정의되어 있어 쿼리 시점에 원본 `events_*` export를 즉시 재계산한다 — GA4 export가 갱신되면 별도 재실행 없이 대시보드에 바로 반영된다. `ab_test_mart`는 Meta Ads·GA4 CSV 파일을 일회성으로 적재한 정적 테이블이라 실시간 갱신 대상이 아니다 (원본 CSV 자체가 스냅샷이므로).

커뮤니티 퍼널: `세션 시작 → 참여 세션 → 아티클 열람 → 가입 클릭 → 가입 완료`

## Quick Start

### 1. 환경 설정

```bash
# Python 백엔드 의존성
pip install -r agent_backend/requirements.txt

# .env 설정
cp agent_backend/.env.example agent_backend/.env
# OPENAI_API_KEY, GCP_PROJECT_ID, GOOGLE_APPLICATION_CREDENTIALS 입력

# Next.js 의존성
npm install
```

### 2. BigQuery Mart 생성

```bash
# GA4 → Mart 변환 (최초 1회 또는 데이터 갱신 시)
GOOGLE_APPLICATION_CREDENTIALS=dashboard/credentials.json \
  python agent_backend/scripts/build_marts.py

# A/B 테스트 데이터 적재 (자료/*.csv 있을 때)
GOOGLE_APPLICATION_CREDENTIALS=dashboard/credentials.json \
  python agent_backend/scripts/load_ab_test_mart.py
```

### 3. 실행

```bash
# 백엔드 (터미널 1)
cd agent_backend
uvicorn main:app --reload

# 프론트엔드 (터미널 2)
npm run dev
# → http://localhost:3000
```

API 직접 호출:

```bash
curl --get --data-urlencode "q=이번 달 퍼널 분석해줘" http://localhost:8000/analyze
```

## Deploy

**Backend (Railway)** — FastAPI + LangGraph 파이프라인은 2~3분 걸려 Vercel 서버리스에 맞지 않으므로 Railway 같은 상시 실행 서버에 올린다. `agent_backend`가 자기 자신을 `agent_backend.xxx`로 패키지 임포트하므로, 배포 루트는 반드시 저장소 루트(`da_agent/`)여야 한다.

1. 저장소 루트에 있는 `railway.json`이 Nixpacks 빌드·시작 명령을 정의한다 (`uvicorn agent_backend.main:app`). 루트 `requirements.txt`는 nixpacks가 Python 프로젝트로 자동 감지하도록 `agent_backend/requirements.txt`를 복사해둔 것이다.
2. `railway init` 또는 `railway link`로 저장소 루트를 프로젝트에 연결 후 `railway up`
3. 환경변수 설정: `OPENAI_API_KEY`, `GCP_PROJECT_ID`, `GOOGLE_CREDENTIALS_BASE64`(서비스 계정 JSON을 `base64 -i credentials.json`으로 인코딩 — `railway.json`의 startCommand가 컨테이너 시작 시 파일로 복원), `BACKEND_SHARED_SECRET`(`openssl rand -hex 32`로 생성)
4. `railway domain`으로 공개 도메인 발급

**Frontend (Vercel)**

1. `dashboard/`를 루트로 Vercel 프로젝트 생성
2. 환경변수 설정: `AGENT_BACKEND_URL`(Railway 도메인), `BACKEND_SHARED_SECRET`(백엔드와 동일 값)
3. `/api/analyze`는 `maxDuration = 300`을 선언하므로 Vercel Pro 플랜이 필요하다 (Hobby는 60초 상한).
4. Project Settings → Deployment Protection이 기본 켜져 있으면 API 라우트까지 Vercel 로그인으로 막힌다 — 공개 서비스라면 꺼야 한다.

`BACKEND_SHARED_SECRET`을 양쪽에 설정하면 FastAPI가 `x-backend-secret` 헤더 없는 요청을 401로 거부한다 — Next.js 프록시를 거치지 않은 직접 호출로 인한 과금 남용을 막기 위함. 로컬 개발에서는 미설정 시 검사를 건너뛴다.

## Directory Structure

```
da_agent/
├── railway.json             # Railway 배포 설정 (Nixpacks build/start)
├── requirements.txt         # nixpacks Python 자동 감지용 (agent_backend/requirements.txt 복사)
├── IMPROVEMENTS.md          # 전체 점검·수정 내역
├── agent_backend/
│   ├── main.py              # FastAPI 진입점 + BACKEND_SHARED_SECRET 미들웨어
│   ├── graph.py             # LangGraph StateGraph
│   ├── state.py             # AnalysisState TypedDict
│   ├── hooks.py             # Stop Hooks (report → PDF → Slack → Email)
│   ├── agents/nodes.py      # 7개 에이전트 노드, knowledge/·skills/ 런타임 로드
│   ├── tools/bigquery.py    # BigQuery tool calling 함수
│   ├── tests/                   # 순수 로직 단위 테스트
│   └── scripts/
│       ├── build_marts.py       # GA4 → Mart VIEW 생성 (실시간)
│       └── load_ab_test_mart.py # Meta CSV × GA4 CSV → ab_test_mart TABLE
├── dashboard/               # Next.js 프론트엔드
│   └── lib/backend.ts       # 공유 시크릿 헤더 부착 fetch 헬퍼
├── knowledge/               # KPI Dictionary, Business Context (SSOT)
├── skills/                  # 분석 스킬 정의
└── agents/                  # 에이전트 역할 정의
```

## Cost

분석 1회당 약 **$0.27–0.29 USD** (GPT-4o · complex 경로 7개 노드 · ~65k tokens)

## Rules

- Mart Only: Raw `events_*` 테이블 직접 쿼리 금지
- KPI SSOT: `knowledge/kpi_dictionary.md` 단일 정의 참조
- QA FAIL / Evaluator FAIL → 결과 출력 불가 (422)
- DELETE · UPDATE · DROP · `credentials.json` 수정 절대 금지
- 백엔드는 `BACKEND_SHARED_SECRET` 헤더 없는 요청 401 거부 — 프록시 우회 직접 호출 차단

## 더 알아보기

전체 점검 과정에서 발견한 설계 결함·버그·수정 내역은 [IMPROVEMENTS.md](IMPROVEMENTS.md)에 정리되어 있습니다.
