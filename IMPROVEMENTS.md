# 개선 내역 (Improvements)

> 프로젝트 전체 점검에서 발견한 문제와 수정 내용을 카테고리별로 정리한 문서.
> 시기: 2026-07-02 ~ 2026-07-03

---

## 1. 설계 결함 수정

### SSOT가 파이프라인에 연결되지 않던 문제 (가장 중요)
- **문제**: `knowledge/kpi_dictionary.md`와 `skills/*.md` 17개 파일이 디스크에만 존재하고, 에이전트는 아무것도 읽지 않았다. "KPI는 Dictionary 단일 정의", "Agent는 Skill의 방법을 따른다"는 핵심 원칙이 문서로만 존재하는 상태였다.
- **수정** (`agent_backend/agents/nodes.py`):
  - 모듈 로드 시 `knowledge/` + `skills/` 문서를 읽어 메모리에 적재.
  - **Product Analyst** → `business_context.md` 전문을 프롬프트에 주입.
  - **Data Scientist** → `kpi_dictionary.md` + Planner가 선택한 스킬 문서(분석 절차·QA 체크리스트·anti-pattern)를 주입.
  - **Planner** → 사용 가능한 스킬 목록을 디스크 기준 자동 생성 (하드코딩 제거).

### funnel_mart가 커뮤니티와 무관한 퍼널로 구성됨
- **문제**: Landing → Scroll → Engage → Convert 4단계 (범용 웹 퍼널).
- **수정** (`agent_backend/scripts/build_marts.py`): 커뮤니티 가입 흐름 5단계로 교체.
  `세션 시작(26) → 참여 세션(23) → 아티클 열람(16) → 가입 클릭(16) → 가입 완료(14)`
- **발견 인사이트**: 최대 이탈 구간은 참여 → 아티클 열람 (30.4%). 아티클 열람 → 가입 클릭은 이탈 0%.

### A/B 테스트만 Next.js에서 BigQuery 직접 호출
- **문제**: 다른 데이터는 모두 FastAPI 경유인데 A/B 테스트만 Next.js가 BigQuery를 직접 조회 — 인증 이중화, 배포 복잡성.
- **수정**: FastAPI에 `/ab-test` 엔드포인트 추가, Next.js는 프록시로 통일. `dashboard/lib/bigquery.ts` 삭제.

---

## 2. 안정성 (크래시·비용 사고 방지)

### 툴 호출 무한 루프 → 비용 상한 없음
- **문제**: `_invoke_with_tools`가 `while True` — LLM이 툴 호출을 멈추지 않으면 GPT-4o 과금이 무한정 발생.
- **수정**: 최대 10라운드 제한. 마지막 라운드는 툴을 제거하고 답변을 강제.

### Evaluator가 LLM 출력 키 누락에 크래시
- **문제**: `c["result"]` 직접 인덱싱 — judge가 키 하나만 빠뜨려도 `KeyError`로 2분짜리 분석 전체가 소멸.
- **수정**: `.get()` + 누락 시 FAIL 집계. 테스트로 고정.

### 파이프라인 예외가 원인 불명 500으로 노출
- **문제**: `/analyze`에 에러 핸들링이 전혀 없었다.
- **수정**: `try/except` + `PIPELINE_ERROR` 응답 + 로깅.

### LLM JSON 파싱 취약
- **문제**: ` ```json ` 블록만 처리 — LLM이 다른 포맷으로 응답하면 `json.loads` 크래시.
- **수정**: `_extract_json` 헬퍼 — ` ``` ` 블록, 앞뒤 설명 텍스트 모두 처리. 테스트 5개로 고정.

---

## 3. 배포·성능

| 문제 | 수정 |
|---|---|
| Vercel 함수 제한(기본 10초) < 파이프라인 2~3분 → 배포 시 무조건 타임아웃 | `/api/analyze`에 `maxDuration = 300` 선언 (Pro 플랜 필요) |
| 차트 데이터를 보려면 LLM 파이프라인 전체($0.3, 2분+)를 돌려야 함 | `/data` 엔드포인트 신설 — LLM 없이 마트 직접 조회, 차트 즉시 렌더 |
| 브라우저 fetch에 타임아웃 없음 → 무한 대기 | 데이터 30초, AI 분석 3분 타임아웃 |
| Stop Hooks(PDF·Slack)가 API 응답을 블로킹 | FastAPI `BackgroundTasks`로 응답 후 실행 |

---

## 4. 대시보드 버그

- **차트 전부 빈 화면**: 프론트가 참조하는 `res.data` 필드가 API 응답에 없었음 → `/api/data` 분리로 해결.
- **가입 전환율 항상 0%**: 프론트가 옛 퍼널 단계명(`Landing`/`Convert`)을 하드코딩 → 새 단계명으로 수정.
- **가짜 변화율**: `↑ 12.4%` 등 하드코딩된 허위 수치 → 실제 집계값으로 교체.
- **파이프라인 UI에 Planner 누락**: 6개 표시 → 8개 노드 반영.

---

## 5. 환각 방지 (데이터 정합성)

- **커뮤니티 CVR 미정의**: `kpi_dictionary.md`에 North Star(`가입 완료 유저 / 세션 시작 유저`) 정의 추가 — A/B 테스트 CVR과 혼용 금지 명시.
- **채널 데이터 신뢰 불가**: UTM 미설정으로 전 트래픽이 Direct 집계 → SSOT와 Product Analyst 프롬프트에 "채널 기반 결론 도출 금지" 경고 주입.
- **business_context.md 템플릿 방치**: `[YOUR SERVICE NAME]` 상태로 에이전트에 전달되고 있었음 → 실제 서비스 내용으로 전면 작성.
- **스킬 문서 구식화**: `funnel_analysis.md`가 옛 4단계 퍼널 기준 → 커뮤니티 5단계로 갱신.

---

## 6. 코드 정리

- 레거시 순차 LLM 체인 `dashboard/lib/agents.ts` (150줄) 삭제 — LangGraph 백엔드로 대체된 후 미사용.
- `dashboard/lib/bigquery.ts` 삭제 — `queryMart`는 `date` 컬럼 없는 테이블에서 크래시하는 버그도 있었음.
- 미사용 `llm_with_bq_tools` 제거.
- `/data`·`/ab-test`의 중복 BigQuery 헬퍼 → 모듈 레벨 `_query`로 통합.
- 서비스명("The Formula") 하드코딩 전면 제거 — 프롬프트·기본 질문·문서·대시보드 헤더.
- `CLAUDE.md` 에이전트 수 오기(6개) → 8개 정정.

---

## 7. BigQuery 0 나누기·크래시 방어 (2차 점검)

- **A/B 요약 SQL 0 나누기**: `tools/bigquery.py`·`main.py`의 `SUM(x) / SUM(y)` 12곳이 분모 0인 기간 조회 시 쿼리 자체를 실패시킴 → 전부 `SAFE_DIVIDE`로 교체.
- **z-test 세션 0 크래시**: `x1 / n1`이 `ZeroDivisionError`를 그대로 던짐 → 세션 0 가드 추가, 에이전트가 읽을 수 있는 `ERROR:` 문자열 반환으로 통일.
- **전역 예외 핸들러**: `/analyze`에만 있던 에러 핸들링을 `/data`·`/ab-test` 포함 전체로 확장 (`@app.exception_handler(Exception)`).
- **journey_mart no-op `HAVING sessions >= 1`** 제거 (GROUP BY 결과는 항상 참).

---

## 8. E2E 실행 검증에서 발견한 크래시 3건

SSOT 주입 이후 실제로 서버를 띄워 질문 2개(퍼널 분석 / A·B 테스트)를 완주시키며 발견:

1. **툴 예외가 파이프라인 전체를 죽임**: Analytics Engineer가 `date` 컬럼 없는 `funnel_mart`에 날짜 범위를 조회하자 BigQuery 400이 그대로 500으로 전파됨 → 툴 실패를 `TOOL ERROR: ...` 문자열로 감싸 에이전트에게 반환, 에이전트가 읽고 다른 방법으로 재시도.
2. **`get_date_range` 설계 오류**: 날짜 컬럼이 없는 스냅샷 테이블(funnel/channel/landing/journey)에 무조건 `SELECT MIN(date)...`를 날림 → 테이블별 실제 날짜 컬럼 매핑(`DATE_COLUMNS`) 추가, 없는 테이블은 "스냅샷 테이블" 안내 반환.
3. **PDF 생성이 조용히 실패 중**: AppleGothic 폰트가 존재는 하지만 fpdf2에서 OS/2 테이블 문제로 로드 불가했고, `multi_cell`이 커서 위치를 명시하지 않아 두 번째 줄부터 폭 0 에러 → 실제 로드 가능 여부를 검증해 폰트 선택(Arial Unicode로 교체), `multi_cell(new_x="LMARGIN", new_y="NEXT")` 추가.

## 9. 대시보드 실제 렌더링 검증에서 발견한 통계 버그

브라우저로 대시보드를 열어 확인하던 중 **참여율이 288.4%**로 표시되는 명백한 오류 발견.

- **원인**: `dashboard_kpi`의 `engagement_rate` 계산이 `COUNTIF(event_name = 'user_engagement')`로 **이벤트 개수**를 세고 있었음. 한 세션에서 `user_engagement`가 여러 번 발생하면 분자가 분모(세션 수)를 넘어 100%를 초과.
- **수정** (`build_marts.py`): `COUNT(DISTINCT ...)`로 세션 단위 집계로 변경. 재실행 후 정상 범위(50.4%) 확인.

---

## 10. 테스트 & 최종 E2E 검증 결과

`agent_backend/tests/test_pure_logic.py` — LLM 없이 검증 가능한 순수 로직 9개:

- `_extract_json`: 일반 JSON / ```json 블록 / bare 블록 / 앞뒤 텍스트 / 실패 케이스 (5개)
- Evaluator 스코어링: 전부 PASS → confidence 100 / 전부 FAIL → verdict FAIL / **키 누락 시 크래시 없이 FAIL 집계** / 빈 체크 → FAIL (4개)

```bash
python -m pytest agent_backend/tests/ -q   # 9 passed
```

**E2E 실행 결과** (수정 반영 후 재실행):

| 질문 | 결과 |
|---|---|
| 퍼널 이탈 구간 분석 | HTTP 200 · 27초 · QA PASS · Eval PASS (confidence 90, risk 6.2%) |
| A/B 테스트 비교 | HTTP 200 · 42초 · QA PASS · Eval PASS (confidence 100, risk 0%) · 추천 B, p<0.001 |

**대시보드 브라우저 렌더링 확인**: 메인 대시보드(8개 에이전트 파이프라인, KPI 카드, 퍼널·채널·코호트 차트, Executive Brief) + `/ab-test` 페이지(Primary/Guardrail 지표, 퍼널 비교, 일별 추이 차트) 모두 정상 렌더링, 콘솔 에러 없음.

---

## 11. 배포 (Railway + Vercel)

`/analyze`는 GPT-4o 8회 호출(회당 ~$0.3)인데 인증 없이 누구나 호출 가능해 공개 배포 시 과금 남용 위험이 있었음.

- **백엔드 (Railway)**: FastAPI + LangGraph는 2~3분 걸려 Vercel 서버리스에 맞지 않아 상시 실행 서버로 분리. `railway.json`(Nixpacks) + 루트 `requirements.txt`로 배포, GCP 서비스 계정을 base64 환경변수로 전달해 컨테이너 시작 시 파일로 복원.
- **프론트 (Vercel)**: `dashboard/`를 그대로 배포, `AGENT_BACKEND_URL`로 Railway 백엔드 연결.
- **공유 시크릿 인증**: `BACKEND_SHARED_SECRET` 미들웨어 추가 — `/health` 제외 전 엔드포인트가 `x-backend-secret` 헤더 검증. Next.js 프록시 3곳(`api/analyze`, `api/data`, `api/ab-test`)이 공통 `backendFetch` 헬퍼로 헤더를 자동 부착. 헤더 없으면 401, 미설정(로컬 개발)이면 검사 스킵 — 실제로 401/200 양쪽 다 검증함.
- **Vercel 배포 보호 해제**: 기본 SSO 보호가 API 라우트까지 막고 있어서 대시보드 접근 자체가 불가능했음 — Deployment Protection 끄고 공개 전환.
- **최종 프로덕션 E2E 검증**: Vercel → Railway → BigQuery 전체 경로로 `/analyze` 실행, HTTP 200·28초·QA PASS·Eval PASS(confidence 100, risk 0%) 확인.

배포 URL: 프론트 `https://dashboard-leegahees-projects.vercel.app`, 백엔드 `https://da-agent-backend-production-99f0.up.railway.app`

## 12. GA4 마트를 배치 스냅샷 → 실시간 VIEW로 전환

- **문제**: `build_marts.py`가 `DROP TABLE + CREATE TABLE AS SELECT`로 매번 스냅샷을 떠서, GA4에 새 이벤트가 쌓여도 스크립트를 재실행하기 전까지 대시보드에 반영되지 않았음.
- **수정**: GA4 기반 6개 마트(dashboard_kpi·funnel_mart·marketing_channel_mart·landing_page_mart·journey_mart·cohort_mart)를 `CREATE OR REPLACE VIEW`로 전환 — 쿼리 시점마다 원본 `events_*`를 즉시 재계산해 GA4 export 갱신이 곧바로 반영됨. TABLE→VIEW 타입 전환 충돌 방지용 `DROP TABLE IF EXISTS` 선행 처리.
- `ab_test_mart`는 정적 CSV 적재분이라 TABLE로 유지 — 원본 자체가 스냅샷이라 뷰로 바꿔도 실시간성 이득 없음.
- **트레이드오프**: 뷰에 날짜 필터(`_TABLE_SUFFIX`)가 없어 조회마다 전체 히스토리를 재스캔함. 현재 데이터량(443KB/쿼리)에서는 무해하나, 데이터가 크게 늘어나면 스캔 비용이 누적 데이터량에 비례해 계속 커지는 구조 — 예산 캡을 걸어둔 상태라 현재는 보류.

## 13. 대시보드 잔여 데모 흔적 제거

- **문제**: 실제 배포되어 진짜 BigQuery 데이터로 동작하는데도 헤더에 `DEMO` 배지, `2025.06.01~06.27` 하드코딩 날짜, 정적 `QA PASS` 라벨이 남아있었음. 여러 차례 "The Formula" grep으로는 걸러지지 않던 잔재로, 실제 배포 후 눈으로 확인하고 나서야 발견.
- **수정**: `DEMO` 배지 삭제, 날짜 범위를 `dashboard_kpi` 실제 데이터 최소/최대값으로 표시, QA 라벨을 Head of Data 응답의 실제 `qa_verdict`로 표시(PASS/WARN/FAIL 색상 분기).

## 14. 파이프라인 아키텍처 정리 — Supervisor 도입 + 죽은 노드 제거 (2026-07-09~10)

각 노드가 "실제로 하는 일"을 E2E 실행으로 검증하면서, 이름만 에이전트였던
노드를 제거하고 진짜 라우팅 노드를 추가함.

- **Supervisor 추가**: 파이프라인 맨 앞에서 질문을 nonanalytic/simple/complex로
  분류해 실행 경로 자체를 분기. 인사말 등 비분석 질문은 에이전트를 아예 안 돌리고,
  단순 조회는 Data Scientist+Evaluator+Head of Data만, 원인 분석은 전체 체인.
  기존 Planner의 `agents` 필드가 하려다 실패한 "동적 라우팅"을 실제로 실행에
  반영하는 유일한 지점. LLM 호출 실패/비-dict 출력에도 complex로 안전 fallback.
- **BI Analyst 제거**: 검증된 결과를 대시보드용 chart_data JSON으로 재구성하는
  노드였으나, ① 대시보드는 `/data`(마트 직접 SELECT)로 이미 차트를 그리고 있어
  출력을 아무도 안 읽었고 ② 애초에 "AI는 데이터를 생성하지 않는다"는 프로젝트
  원칙과 정면 충돌(LLM이 차트 숫자를 생성). 원칙을 지키려면 마트 직접 조회가
  맞고, 그러면 이 노드는 존재 이유가 사라짐 → 제거. complex 경로 LLM 호출 1회 감소.
- **Planner 제거**: 유일한 산출물 `skills`가 Data Scientist 일반 분기에만
  주입됐는데, 유효 선택지가 skills/analytics/ 5개뿐이고 A/B는 DS가 키워드로
  자체 판별하므로 LLM 선택의 실익이 없었음. 오히려 19개 전체를 후보로 받아
  다른 카테고리 스킬을 잘못 주입하는 버그가 있었음. skills/analytics/ 문서를
  DS가 직접 주입(GENERAL_ANALYSIS_SKILLS)하도록 바꾸고 노드 제거.
- **Evaluator 빈 차원 버그**: hallucination_risk를 항상 (numeric+llm)/2로 평균내
  숫자 주장이 없는 질문(여정 등)이 근거 완벽해도 risk 50%(WARN)를 맞던 버그 수정.
  검증한 차원만 평균에 포함하도록.
- **순수 로직 테스트 확대**: 9개 → 18개. Supervisor fallback, graph._route 방어,
  Evaluator 회귀 등 LLM 없이 검증 가능한 것들 추가.

결과: "8 에이전트"에서 Supervisor +1, Planner·BI Analyst -2 = 실질 노드 7개.
도구를 스스로 호출하는 자율 에이전트는 여전히 3개(Analytics Engineer·Data
Scientist·Evaluator).

## 15. 노드별 전수 점검 — "이름값 못 하던" 검증/게이트 노드 실제화 (2026-07-10)

각 노드가 실제로 무슨 일을 하는지 E2E 실행으로 하나씩 검증. 문서상 역할과
실제 동작이 어긋난 곳을 바로잡음. 관통 주제 = "LLM이 만들면 안 되는 걸 LLM이
만들던 것"과 "게이트라면서 실제로 안 막던 것".

- **LLM 호출 실패 방어 일원화**: 기존엔 무방비였던 노드들(complex 경로 중간
  rate limit 한 번에 파이프라인 크래시)을 `_invoke_json`/`_invoke_with_tools`
  헬퍼 두 곳에서 방어. 실패 시 예외 대신 {"error":...} dict 반환 → gate 노드는
  FAIL로 안전 정지, 나머지는 빈 분석으로 이어짐. 전 노드 자동 보호.
- **Analytics Engineer를 진짜 게이트로**: "게이트키퍼"라면서 trust_level을
  아무도 안 읽어 LOW여도 통과시켰음. ①프롬프트 강화(작은 표본은 HIGH 금지 →
  11일·38명 데이터가 이제 MEDIUM/LOW로) ②`_trust_gate` 추가(LOW면 Data Scientist
  전에 중단) ③main.py DATA_TRUST_LOW 422. 채널(UTM 미설정) 질문이 분석 시작
  전에 차단됨 — 이전에 엉뚱한 답을 만들던 문제를 근본 차단.
- **QA Reviewer 판정 기준 구체화**: "consistency 검증"만 있어 사실상 항상 PASS
  찍던 노드. 구체 체크 3개(수치가 AE 조회 범위 안인지 / trust 낮은데 과신하는지 /
  evidence와 root_cause 모순인지)로 강화. 내부모순→FAIL, 작은표본 과신→WARN 실측
  확인. ensure_ascii=False 누락(한글 \uXXXX 이스케이프)도 수정.
- **Head of Data 환각 차단**: confidence/qa_verdict를 LLM이 출력하고 대시보드가
  QA 배지로 표시했는데, 실측 결과 Evaluator가 코드로 92.9를 계산했는데 LLM은
  50이라 지어냄. 이 두 값을 LLM 출력에서 빼고 실제 계산값(Evaluator confidence,
  QA verdict)으로 코드에서 덮어씀 — "환각 점수는 코드가 계산" 원칙 준수.
- **Supervisor 방어**: 모든 요청의 첫 관문(SPOF)이라 실패 시 complex fallback +
  비-dict 출력 방어. "이탈률"처럼 여러 마트에 걸치는 모호 지표는 simple 대신
  complex로 보내는 가드레일 추가.
- **테스트 18 → 23개**: trust_gate, QA 판정, Head of Data 주입 등 회귀 커버.

교훈: 스스로 세운 원칙("AI는 데이터/점수를 생성하지 않는다")에 비춰 자기 코드를
검증하니, 그 원칙을 위반하던 노드가 반복적으로 드러났다(BI Analyst=차트 생성,
Head of Data=신뢰도 생성). 검증 계층(QA/Eval/trust 게이트)이 "있다"와 "실제로
작동한다"는 다른 문제.

---

## 남은 과제

- [ ] **UTM 파라미터 세팅** — 채널 분석이 의미를 가지려면 유입 링크에 UTM 필요 (코드 밖 이슈).
- [ ] **뷰 날짜 필터링** — 데이터량이 늘어나면 `_TABLE_SUFFIX` 범위 제한으로 스캔 비용 상수화 검토 (현재는 예산 캡으로 보류 중).
- [ ] **ab_test_mart 커뮤니티 버전** — 현재 e-commerce 컬럼(purchases 등) 기반. form_start/form_submit 기반으로 교체 검토.
- [ ] **Mann-Whitney U test** — 연속형 지표(체류시간 등) 유의성 검정 추가 검토.
