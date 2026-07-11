# AI Data Team OS — 프로젝트 완전 해부 & 포트폴리오(Project 03) 보완 가이드

> 코드 전체(backend 1,000+ 라인, frontend 500+ 라인, knowledge/skills 문서 22개)와
> portfolio_work.pdf 13~16p(Project 03)를 대조해 작성. 2026-07-03.

---

# PART 1. 프로젝트 완전 해부

## 1. 한 줄 정의

GA4 → BigQuery로 쌓인 커뮤니티 웹사이트 데이터를, **LangGraph 기반 8개 AI 에이전트**가 역할을 나눠 tool calling으로 직접 조회·분석하고, **QA + Evaluator 이중 게이트**로 환각을 걸러낸 결과만 Executive Brief로 출력하는 시스템.

## 2. 전체 워크플로우 (요청 1건의 생애주기)

```
[브라우저] dashboard 접속
   ├─ fetch /api/data     (30초 타임아웃)  ← 차트용, LLM 없음
   └─ fetch /api/analyze  (3분 타임아웃)   ← AI 분석
        ↓
[Next.js API Route] app/api/analyze/route.ts
   maxDuration=300 · lib/backend.ts가 x-backend-secret 헤더 부착
        ↓
[FastAPI · Railway] agent_backend/main.py  GET /analyze?q=
   미들웨어: BACKEND_SHARED_SECRET 검증 (불일치 → 401)
   initial_state 생성 → pipeline.ainvoke(state)
        ↓
[LangGraph StateGraph] graph.py — 8 노드 순차 + 조건부 엣지 2개
   Planner → Product Analyst → Analytics Engineer → Data Scientist
   → QA Reviewer ──(FAIL→END, main이 422 반환)
   → Evaluator ──(FAIL→END, 422)
   → BI Analyst → Head of Data → END
        ↓
[응답 직후 백그라운드] BackgroundTasks → hooks.run_stop_hooks
   executive_report.md 생성 → fpdf2로 PDF 변환(한글 폰트 자동탐색)
   → SLACK_WEBHOOK_URL 있으면 Slack 알림
        ↓
[JSON 응답] { pipeline: {각 에이전트 출력}, brief: head_of_data, ... }
```

## 3. 파일별 역할 (전부)

### agent_backend/ — 두뇌
| 파일 | 라인 | 역할 |
|---|---|---|
| `main.py` | 152 | FastAPI 진입점. 4개 엔드포인트(`/analyze` `/data` `/ab-test` `/health`), 공유 시크릿 미들웨어, 전역 예외 핸들러(500+원인), QA/Eval FAIL→422, Stop Hooks 예약 |
| `graph.py` | 54 | StateGraph 정의. 8노드 + `_qa_gate`/`_eval_gate` 조건부 엣지. verdict 키 누락 시 기본값 FAIL(안전한 쪽으로) |
| `state.py` | 14 | `AnalysisState` TypedDict — 에이전트 8칸 + question + error. 모든 노드가 이 공유 상태를 읽고 자기 칸만 채움 |
| `agents/nodes.py` | 390 | **핵심.** 8개 노드 함수 + 공통 인프라: ① 모듈 로드 시 `knowledge/`·`skills/` md를 메모리 적재(SSOT 런타임 주입) ② `_extract_json` — 마크다운 블록/앞뒤 잡설 섞인 LLM 응답에서 JSON만 추출 ③ `_invoke_with_tools` — tool calling 루프, MAX 10라운드(비용 상한), 마지막 라운드엔 툴 제거하고 답변 강제, 툴 예외는 에러 문자열로 에이전트에 반환(크래시 대신 재시도 유도) |
| `tools/bigquery.py` | 125 | LangChain `@tool` 4개: `query_mart`(화이트리스트 테이블만 SELECT LIMIT 500), `get_date_range`, `get_ab_test_summary`(변형별 집계+파생지표 SSOT), `run_ab_significance_test`(two-proportion z-test를 **파이썬 math.erfc로 결정론적 계산** — LLM p-value 추정 원천 차단) |
| `hooks.py` | 134 | Stop Hooks 구현: md 리포트 조립 → fpdf2 PDF(폰트 후보를 실제 `add_font` 프로브로 검증 — AppleGothic처럼 존재해도 로드 실패하는 케이스 방어) → Slack webhook. 각 단계 실패해도 다음 단계 진행 |
| `scripts/build_marts.py` | 230 | GA4 raw `events_*` → 마트 6개를 **VIEW로** 생성(쿼리 시점 재계산 = 실시간). 유일하게 raw를 만지는 관리자 스크립트 |
| `scripts/load_ab_test_mart.py` | 103 | Meta Ads CSV + GA4 CSV → BigQuery 적재 → `join_key`(date×variant)로 조인해 `ab_test_mart` **TABLE** 생성(원본이 정적 스냅샷이라 VIEW 아님) + 기대값 검증 출력 |
| `tests/test_pure_logic.py` | — | 순수 로직 테스트 9개(JSON 추출, Evaluator 점수 계산 등 환각 방지 핵심 커버) |

### dashboard/ — 얼굴
| 파일 | 역할 |
|---|---|
| `app/page.tsx` (280) | 메인 대시보드. `/api/data`(즉시)와 `/api/analyze`(2~3분)를 **분리 fetch** — 차트 먼저 뜨고 AI 브리핑은 나중에. KPI 카드 4개, Executive Brief, 퍼널/채널/랜딩/코호트 차트(전부 API 데이터만 렌더) |
| `app/ab-test/page.tsx` (195) | A/B 리포트. Primary 3지표(GO/NO-GO), Guardrail 3지표(>10% 악화 시 DEGRADED), 변형별 6단계 퍼널, CVR·ROAS 일별 SVG 추이. 승자 판정 로직이 프론트에도 미러링됨 |
| `app/api/{analyze,data,ab-test}/route.ts` | 순수 프록시 — 시크릿 헤더 붙여 FastAPI로 전달. `analyze`만 `maxDuration=300` |
| `lib/backend.ts` | 백엔드 fetch 공통 헬퍼(시크릿 부착) |

### 문서 계층 (에이전트가 실제로 읽는 것 vs 사람용)
- **런타임 주입(SSOT)**: `knowledge/kpi_dictionary.md`(지표 정의+A/B 지표+"UTM 미설정으로 채널 신뢰 불가" 경고까지), `knowledge/business_context.md`(가입=전환, e-commerce 가정 금지), `skills/*.md` 17개(분석 절차·QA 체크리스트·anti-pattern — Planner가 고른 것만 Data Scientist 프롬프트에 주입)
- **사람용**: README, IMPROVEMENTS(개선 이력), CLAUDE.md(작업 규칙), config/workflows.yaml(설계 명세), agents/*.md(역할 정의), architecture.md(⚠️ 구버전)

## 4. 8개 에이전트 상세

| # | 노드 | LLM 호출 방식 | 프롬프트에 주입되는 것 | 출력(state 칸) |
|---|---|---|---|---|
| 1 | Planner | JSON 단발 | 디스크에서 자동 생성한 스킬 목록 | 필요한 agents/skills 선택 + 이유 |
| 2 | Product Analyst | JSON 단발 | **business_context.md 전문** | headline·focus_metrics·가설·분석방향 |
| 3 | Analytics Engineer | **tool calling** | query_mart, get_date_range | trust_level(H/M/L)·issues·confidence |
| 4 | Data Scientist | **tool calling** | **kpi_dictionary.md + 선택된 skill 문서**. A/B 질문이면 전용 분기(z-test 툴 강제, Primary/Guardrail/Funnel 프레임, "모든 Primary가 유의하게 B 우세 + Guardrail 10% 이내일 때만 B 추천" 규칙) | root_cause·인사이트·evidence / A/B면 p-value·추천 변형 |
| 5 | QA Reviewer | JSON 단발 | 앞 3개 에이전트 출력 전부 | verdict PASS/WARN/FAIL — **FAIL이면 여기서 파이프라인 종료** |
| 6 | Evaluator | tool calling(judge) + **파이썬 점수 계산** | Data Scientist의 모든 주장 → 마트 **재조회 대조**(수치 ±2% 허용) | Confidence·Hallucination Risk·Grounded.Numeric/LLM·verdict·investigation_log — **FAIL이면 종료** |
| 7 | BI Analyst | JSON 단발 | QA 통과 수치만 | 대시보드용 kpi_summary·chart_data |
| 8 | Head of Data | JSON 단발 | 전 파이프라인 출력(로그 제외) | 한국어 Executive Brief — headline + 인사이트 3 + 액션 3 |

**Evaluator 산식** (LLM이 아니라 코드가 계산 — 이 프로젝트의 최대 차별점):
- Grounded.Numeric = (PASS×1 + PARTIAL×0.5) / 수치 주장 수 × 100
- Grounded.LLM = (YES×1 + PARTIAL×0.5) / 정성 진술 수 × 100
- Hallucination Risk = 100 − (두 Grounded 평균)
- Confidence = (PASS + PARTIAL×0.5) / 전체 체크 × 100
- PASS: Conf≥70 ∧ Risk≤30 · WARN: Conf≥50 ∧ Risk≤50 · 그 외 FAIL

## 5. BigQuery 마트 7개

| 마트 | 타입 | 내용 | 핵심 SQL 포인트 |
|---|---|---|---|
| dashboard_kpi | VIEW | 일별 users/sessions/PV/참여율/스크롤율/체류시간/재방문 | 세션 = `CONCAT(user_pseudo_id, ga_session_id)` DISTINCT — **288.4% 버그를 고친 그 지점** |
| funnel_mart | VIEW | 커뮤니티 5단계: 세션 시작→참여→아티클 열람→가입 클릭(form_start)→가입 완료(form_submit) | drop_off_rate를 `LAG` 윈도우로 사전 계산 |
| marketing_channel_mart | VIEW | traffic_source.medium → 6채널 그룹 | UTM 미설정이라 사실상 전부 Direct(SSOT에 경고 명시) |
| landing_page_mart | VIEW | 페이지별 PV/스크롤율/체류시간 | page_location에서 path만 REGEXP 추출, PV≥3 필터 |
| journey_mart | VIEW | 세션 내 page_view 시퀀스 " → " 연결 | ⚠️ 버그 있음(아래 7절) |
| cohort_mart | VIEW | first_visit 주차 코호트 × 주차별 리텐션 | DATE_TRUNC WEEK + DATE_DIFF |
| ab_test_mart | TABLE | Meta(노출·클릭·비용) × GA4(세션·ATC·구매·매출) join_key 결합 | 원본이 정적 CSV라 TABLE 유지 |

## 5-1. 실데이터 vs 합성데이터 경계 (2026-07-09 확인)

BigQuery에 있는 9개 테이블 중 실제로 무엇이 진짜 데이터고 무엇이 시드된 합성 데이터인지 `INFORMATION_SCHEMA`로 직접 검증함.

| 구분 | 대상 | 근거 |
|---|---|---|
| **실데이터** | `dashboard_kpi`, `funnel_mart`, `marketing_channel_mart`, `landing_page_mart`, `journey_mart`, `cohort_mart` (6개) | 전부 VIEW이고 소스가 `analytics_543337410.events_*`. 이 원본이 실제로 `events_20260627`~`events_20260707` 11일치·1,751개 이벤트뿐임을 `_TABLE_SUFFIX` 집계로 확인. `dashboard_kpi`를 직접 SELECT해서 11행/2026-06-27~07-07이 나오는 것도 재확인 완료 |
| **합성데이터** | `ga4_landing_src`, `meta_ads_src`, `ab_test_mart` (3개) | `ga4_landing_src`/`meta_ads_src`는 CSV 수동 적재본으로 2026-01-01~04-10 기간에 정확히 20,000행씩, `property_id=987654321`·계정명 "JU DATA Demo Account" 등 시드 흔적 뚜렷함. `ab_test_mart`는 이 둘을 join_key로 합친 파생물이라 마찬가지로 합성 |

**포트폴리오 서사 원칙**: 실데이터 6개 마트는 "실 GA4 이벤트를 파싱·집계하는 파이프라인이 정상 동작한다"는 엔지니어링 증거로 쓰고, 표본이 작아(11일) 코호트/채널 비교 등 통계적 인사이트 도출 용도로는 쓰지 않는다. 합성 3개(A/B 테스트 쪽)는 "실험 설계+z-test 방법론을 구현할 줄 안다"는 용도로만 쓰고 발표 시 합성 데이터임을 명시한다. 두 용도를 섞어서 말하지 않는다.

## 6. 배포·보안 구성

- Frontend: Vercel / Backend: Railway 상시 실행 (서버리스 시간·용량 한계 회피 — 실측 27~42초 파이프라인)
- 인증: `BACKEND_SHARED_SECRET` 공유 시크릿 — Next.js 프록시만 백엔드 호출 가능, 직접 호출 401 (미설정 시 로컬 개발용 스킵)
- 시크릿 관리: `.env`·`credentials.json` 모두 .gitignore 처리 확인됨
- 비용: 1회 분석 ≈ $0.27~0.29 (GPT-4o 8회, ~65k tokens), 툴 루프 10라운드 상한

## 7. 내가 발견한 현재 문제점 (코드 기준, 우선순위순)

### 🔴 데이터 정합성
1. **journey_mart 집계 버그** — `GROUP BY user_pseudo_id, session_id`라서 결과가 "경로별 세션 수"가 아니라 **세션 1건당 1행**이고, `COUNT(*) AS sessions`는 실제로는 그 세션의 page_view 수. 같은 경로가 합쳐지지 않아 "가장 흔한 여정 TOP N" 분석이 불가능. → 바깥에서 `GROUP BY path` 한 겹 더 필요.
2. **dashboard_kpi의 returning_users 산식 의심** — `(first_visit 없는 유저 수) − (first_visit 있는 유저 수)`는 재방문자 정의와 다르고 음수도 가능. cohort 기반 정의(kpi_dictionary의 session_count>1)와도 불일치.

### 🟠 제품/비용
3. **질문 입력 UI가 없음** — "질문 하나를 입력하면"이 핵심 스토리인데 대시보드에 입력창이 없고 기본 질문 하나만 자동 실행됨. `q` 파라미터는 이미 전 구간 지원되므로 input 하나만 붙이면 됨.
4. **페이지 로드마다 /analyze 자동 호출** — 방문자 1명 = GPT-4o 8회($0.27) + 2~3분 대기. 결과 캐싱(같은 질문 N분 캐시)이나 "분석 실행" 버튼 전환이 필요. 포트폴리오 공개 링크로 트래픽이 오면 그대로 과금.
5. **Planner의 선택이 실행에 반영 안 됨** — workflows.yaml에는 "0 스킬이면 skip"이 명세돼 있지만 graph.py는 고정 엣지라 항상 8개 전부 실행. skills 선택은 프롬프트에 반영되지만 agents 선택은 장식.
6. **BI Analyst 출력 미사용** — 대시보드는 `/data` 직접 조회로 차트를 그리고, bi_analyst의 chart_data는 아무도 렌더하지 않음(LLM 호출 1회 낭비).

### 🟡 보안(문자 그대로의 보안)
7. **SQL 인젝션 경로** — `get_ab_test_summary`·`run_ab_significance_test`의 start_date/end_date가 f-string으로 SQL에 직결. LLM이 넘기는 값이지만 프롬프트 인젝션 경유 가능. → BigQuery `ScalarQueryParameter` 또는 `YYYY-MM-DD` regex 검증.
8. **시크릿 비교 타이밍 안전 X** — `!=` 대신 `hmac.compare_digest` 권장.
9. **GET에 부수효과 + 레이트리밋 없음** — /analyze는 과금이 발생하는 무거운 연산인데 GET이고 호출 횟수 제한이 없음.

### ⚪ 표시/문서 불일치 (GitHub 공개 시 신뢰도 이슈)
10. 대시보드 파이프라인 위젯이 **7개만 표시(Evaluator 누락)** — 포트폴리오는 "8-에이전트"라고 주장. 게다가 상태 표시가 실제 진행과 무관한 가짜(⏳→✓).
11. 에러 문구 `"ANTHROPIC_API_KEY를 확인하세요"` — 실제 백엔드는 OpenAI.
12. `workflows.yaml model: claude-sonnet-4-6`, `PROJECT.md "AI Agent: Claude"` — 실제는 gpt-4o.
13. `architecture.md` 전체가 존재하지 않는 구버전 구조(lib/agents.ts, services/*, Ask Your Data 탭) 설명. `PROJECT.md` 진행 체크리스트도 "에이전트 파이프라인 구축 [ ]" 미완료 상태로 방치.
14. hooks 산출물이 고정 파일명 덮어쓰기 — 동시 요청 시 경합, 이력 유실.

---

# PART 2. 포트폴리오 Project 03 (13~16p) 보완

## 잘된 점 (유지)
- "이름만 멀티 에이전트였던 걸 진짜로 만들었다"는 Before→After 프레임 — 문제 정의가 명확하고 정직함
- 288.4%→50.4% 같은 물리적으로 불가능한 수치를 잡은 훅
- 결정의 근거 4건(LangGraph vs 체인 / Railway vs Vercel / VIEW vs TABLE / z-test 결정론) — dry_run 443KB 실측까지 붙인 건 세 프로젝트 중 가장 설득력 있는 표
- "문서화 ≠ 실제 사용", "로컬 테스트 통과 ≠ 실전 안정성" 배운 점 — 채용자가 좋아할 문장들

## 🔧 수정할 부분

1. **코드-포트폴리오 불일치부터 제거 (최우선)** — GitHub 링크와 라이브 데모 뱃지를 달아놨기 때문에 검증하는 순간 다음이 바로 보임:
   - 대시보드 에이전트 위젯 7개 vs 본문 "8-에이전트" → Evaluator 추가
   - "ANTHROPIC_API_KEY" 에러 문구 vs GPT-4o 스택 표기
   - repo의 architecture.md·PROJECT.md·workflows.yaml이 전부 구버전 → 특히 "문서화 ≠ 실제 사용을 배웠다"고 써놓고 repo 문서가 낡아있으면 그 배움 자체가 반박됨. 삭제하거나 갱신 필수.
2. **"질문 하나를 입력하면" 서사 vs 입력창 없는 데모** — 입력 UI를 붙이거나, 포트폴리오 문구를 "기본 질문 자동 분석"으로 낮추거나 둘 중 하나로 정합 맞추기. (전자를 권함 — 몇 줄이면 됨.)
3. **288.4% 버그의 발견 서사 추가** — 현재는 표에 결과만 있음. "참여율이 100%를 넘는 걸 보고 → 세션 카운트가 CONCAT 없이 COUNT라 중복 집계임을 추적 → COUNT DISTINCT(user×session_id)로 수정"처럼 발견→원인→수정 3박자를 한 줄이라도. 이 포트폴리오의 주제("측정해 원인부터 고친다")와 정확히 맞는 사례인데 아깝게 소비되고 있음.
4. **"13차 리뷰 · 25개 이상 수정" 근거 제시** — 숫자만 있으면 주장(Claimed)이고, Project 02에서 본인이 만든 기준으로는 Verified가 아님. IMPROVEMENTS.md가 이미 카테고리별 정리돼 있으니 "상세 내역: repo IMPROVEMENTS.md" 한 줄로 링크하면 검증 가능한 주장이 됨.
5. **회고 포맷 통일** — P1·P2는 잘한 점/아쉬운 점/다시 한다면 3단인데 P3만 "배운 점 4개"로 구조가 다름. 아쉬운 점(예: Planner의 skip 로직 미구현, 결과 캐싱 부재로 호출당 $0.27, UTM 미설정으로 채널 분석 봉인)과 다시 한다면(스트리밍 진행 표시, 평가 파이프라인 상시 관측 통합)을 추가하면 P2와 같은 밀도가 됨. 특히 **한계를 스스로 공개하는 것**이 이 포트폴리오의 톤인데 P3만 성과로 끝남.

## ➕ 추가할 부분

1. **결과물 스크린샷** — P1은 아키텍처 다이어그램, P2는 라이브 데모 출력 캡처가 있는데 P3만 이미지가 없음. Executive Brief 카드 + A/B 리포트(Primary/Guardrail/퍼널) 캡처 1~2장. "대시보드는 API 결과만 렌더" 원칙도 캡션으로.
2. **Evaluator 산식 공개** — 이 프로젝트의 진짜 차별점은 "환각 점수를 LLM이 아니라 코드가 계산"인데, 현재 PDF에는 Risk 0~6.2% 결과만 있고 **어떻게 계산되는지**가 없음. `Grounded.Numeric(±2% 대조) · Grounded.LLM · Risk = 100−평균 · Conf≥70∧Risk≤30→PASS` 한 박스면 충분. P2에서 신뢰도 3등급 판정 박스를 넣은 것과 대칭.
3. **파이프라인 그래프 다이어그램** — P2에는 dispatcher→평가자들→consensus 그래프가 있는데 P3는 텍스트뿐. 조건부 엣지(QA FAIL→422, Eval FAIL→422)가 보이는 8노드 그래프 하나가 "진짜 멀티 에이전트" 주장을 시각적으로 증명함.
4. **비용 엔지니어링 한 줄** — $0.27~0.29/run 실측, 툴 루프 10라운드 상한, 차트용 `/data` 분리로 "차트 보는 데 LLM 비용 0". 운영 감각을 보여주는 소재인데 repo에만 있고 PDF에 없음.
5. **(선택) SSOT 런타임 주입 도식** — knowledge/skills 문서가 프롬프트로 주입되는 흐름. "문서가 곧 코드"라는 설계를 P3의 핵심 문제 1(SSOT 미연결)과 연결해 시각화.

## 요약 우선순위

| 순위 | 액션 | 이유 |
|---|---|---|
| 1 | repo 구버전 문서 정리 + 프론트 불일치 3건 수정 | 링크 타고 오는 검증자에게 즉시 노출 |
| 2 | 질문 입력 UI + 결과 캐싱 | 핵심 서사 정합 + 공개 데모 과금 방어 |
| 3 | Evaluator 산식 박스 + 파이프라인 다이어그램 추가 | 최대 차별점이 현재 안 보임 |
| 4 | 288.4% 발견 서사 + 회고 3단 통일 | 스토리 밀도 P2 수준으로 |
| 5 | journey_mart 버그 수정, SQL 파라미터화 | 코드 품질 (면접 때 지적당하기 전에) |
