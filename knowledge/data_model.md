# Data Model — Mart ERD

## BigQuery Dataset: formula_silk_analytics

> 실제 컬럼은 `agent_backend/scripts/build_marts.py`(GA4 실데이터 VIEW)와
> 실험 마트 생성 스크립트가 SSOT. 이 문서는 그 결과 스키마를 반영한다.
> GA4 기반 마트는 VIEW(조회 시점 재계산), 실험 마트와 run_log는 TABLE.

### dashboard_kpi (VIEW)
| Column | Type | Description |
|---|---|---|
| date | DATE | event date |
| users | INT64 | daily unique users |
| sessions | INT64 | daily sessions |
| page_views | INT64 | daily page views |
| engagement_rate | FLOAT64 | engaged sessions / total sessions |
| scroll_rate | FLOAT64 | scroll events / page views |
| avg_engagement_time_sec | FLOAT64 | avg engaged time per user |
| returning_users | INT64 | users with >1 session |

### funnel_mart (VIEW) — 2026-07-09 재설계
| Column | Type | Description |
|---|---|---|
| cohort_date | STRING(YYYYMMDD) | 유저 첫 방문일 코호트 (날짜별 퍼널 비교용) |
| funnel_step | STRING | 방문 / 콘텐츠 소비 / 가입 페이지 도달 / 로그인·가입 시도 / 가입 완료 |
| step_order | INT64 | 1~5 |
| users | INT64 | 해당 코호트에서 이 단계까지 도달한 유저 수 (누적 순차) |
| drop_off_rate | FLOAT64 | 직전 단계 대비 이탈률 (코호트별 사전 계산) |

### marketing_channel_mart (VIEW)
| Column | Type | Description |
|---|---|---|
| date | STRING(YYYYMMDD) | event date |
| channel_group | STRING | Organic Search / Paid Search / Social / Referral / Email / Direct |
| sessions | INT64 | sessions from this channel |
| users | INT64 | users from this channel |
| engagement_rate | FLOAT64 | 참여 세션 / 전체 세션 (⚠️ UTM 미설정 → 거의 Direct, 신뢰도 LOW) |

### landing_page_mart (VIEW)
| Column | Type | Description |
|---|---|---|
| date | STRING(YYYYMMDD) | event date |
| page_path | STRING | URL path |
| page_views | INT64 | views per page (일별, HAVING >=1) |
| scroll_rate | FLOAT64 | scroll events / page views |
| avg_engagement_time_sec | FLOAT64 | avg engaged time per user on page |

### journey_mart (VIEW)
| Column | Type | Description |
|---|---|---|
| path | STRING | 한 세션의 페이지 이동을 "A → B → C"로 이은 문자열 |
| sessions | INT64 | 그 경로를 밟은 세션 수 (TOP 200) |
> from_page/to_page 컬럼 없음 — 경로는 문자열 하나. 날짜 차원 없음(전체 기간 스냅샷).

### cohort_mart (VIEW)
| Column | Type | Description |
|---|---|---|
| cohort_week | DATE | week user first visited (first_visit 기준) |
| week_number | INT64 | weeks since first visit (0=acquisition) |
| users | INT64 | users retained this week |
| retention_rate | FLOAT64 | retained / cohort_size |

### search_query_mart (VIEW) — 콘텐츠 갭 신호
| Column | Type | Description |
|---|---|---|
| query | STRING | 사이트 내 검색어 (url_decode UDF로 한글 디코딩) |
| search_count | INT64 | 검색 횟수 |
| search_sessions | INT64 | 검색이 발생한 세션 수 |
| led_to_article | INT64 | 검색 후 같은 세션에서 아티클 조회로 이어진 수 |
| no_click_rate | FLOAT64 | 결과 클릭 없이 끝난 비율 (높을수록 콘텐츠 갭) |

### recommendation_mart (VIEW)
| Column | Type | Description |
|---|---|---|
| article_id | STRING | 추천이 노출된 아티클 |
| shown | INT64 | recommendation_shown 이벤트 수 |
| clicked | INT64 | recommendation_click 이벤트 수 |
| click_through_rate | FLOAT64 | clicked / shown |
> ⚠️ 기능(해시태그 관련 글 추천) 미배포 상태라 현재 0행이 정상 — 계측 공백 감시 대상.

### signup_prompt_experiment_mart / home_sort_experiment_mart (TABLE, 목업)
> A/B 실험 설계를 담은 **목업 데이터**(random 생성). 실기능 배포 후 실데이터 VIEW로 교체 예정.
> 공통 컬럼: `date`, `variant`(A/B), numerator/denominator 계열(실험별 상이) + guardrail.
> 상세 컬럼·의미는 `knowledge/ab_test_framework.md` §6 및 EXPERIMENT_METRICS 참조.

### run_log (TABLE)
> 매 /analyze 실행 1행 기록(관측용): ts, question, route, outcome, trust_level,
> qa_verdict, eval_verdict, confidence, hallucination_risk, latency_ms.

## Join / Grain 주의
- 마트마다 시간 차원이 다르다: `date`(kpi/channel/landing/실험), `cohort_date`(funnel),
  `cohort_week`(cohort), 없음(journey/recommendation/search). 무조건 `date`로 조인 금지.
- User/Session 레벨 조인 키(`user_pseudo_id`, `ga_session_id`)는 Raw 전용 — 마트 조회에선 사용 안 함.

## Mart Access Rules
- 에이전트는 `query_mart(table_name)`로만 접근 (MART_TABLES 화이트리스트).
- Raw `events_*` 직접 접근 금지 (마트 생성 SQL에서만).
- LIMIT은 query_mart가 자동 부여(500).
