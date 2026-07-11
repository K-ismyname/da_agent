# GA4 raw events_* → formula_silk_analytics mart 변환 스크립트
# VIEW로 생성 — 쿼리 시점에 원본 events_*를 즉시 재계산하므로 GA4 export가
# 갱신되는 대로 실시간 반영됨 (배치 스냅샷 아님).
#
# [역할]
# CLAUDE.md "Mart only" 원칙의 데이터 준비 단계. 에이전트/도구는 절대
# Raw events_* 테이블에 직접 접근하지 않으므로, 그 대신 조회할 6개 마트
# (dashboard_kpi ~ cohort_mart)를 여기서 미리(사실은 VIEW라 매 쿼리 시점에)
# events_*를 가공해 만든다. 한 번 실행하면 되는 셋업 스크립트로, 파이프라인
# 요청 경로(main.py)와는 별개로 수동/배치 실행된다.
#
# [왜 TABLE이 아니라 VIEW로 만들었나] (관찰기록 1504 "View-based 마이그레이션")
# 원래는 TABLE로 스냅샷을 만들어 주기적으로 재생성했으나, GA4 export가
# 매일 갱신되는데 스냅샷은 그 시점에 멈춰있어 최신 데이터가 반영 안 되는
# 문제가 있었다. VIEW는 저장된 데이터가 없고 조회 시점에 항상 원본을
# 재계산하므로, 재생성 스케줄 없이 항상 최신 상태를 보장한다(대신 조회
# 비용이 매번 발생 — TABLE보다 쿼리가 느릴 수 있다는 트레이드오프는 있음).
import os
from dotenv import load_dotenv
from google.cloud import bigquery

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

PROJECT = os.environ['GCP_PROJECT_ID']
SRC = f"`{PROJECT}.analytics_543337410.events_*`"
DEST = f"{PROJECT}.formula_silk_analytics"

client = bigquery.Client()


def run(table: str, sql: str):
    """마트 하나를 VIEW로 (재)생성하고 행 수를 출력하는 공통 헬퍼.
    이 스크립트의 6개 마트 정의가 전부 SQL 문자열만 다르고 실행 절차는
    똑같아서, 반복을 피하려고 공통 함수로 뽑아냈다."""
    dest = f"{DEST}.{table}"
    try:
        # 이전에 TABLE로 만들어진 적 있으면 제거 (VIEW로는 CREATE OR REPLACE 불가)
        # — TABLE→VIEW 마이그레이션 과거 이력 때문에 필요한 하위호환 처리
        client.query(f"DROP TABLE IF EXISTS `{dest}`").result()
    except Exception:
        pass  # 이미 VIEW인 경우 타입 불일치로 무시됨 — 정상
    client.query(f"CREATE OR REPLACE VIEW `{dest}` AS\n{sql}").result()
    rows = list(client.query(f"SELECT COUNT(*) AS n FROM `{dest}`").result())[0]['n']
    print(f"{table}: view 생성 (실시간) · 현재 {rows}행")


# ── 1. dashboard_kpi ─────────────────────────────────────────────────
# 일자별 핵심 지표(사용자수/세션수/페이지뷰/참여율 등)를 한 행씩 집계.
# 대시보드 메인 화면과 Analytics Engineer가 가장 먼저 참조하는 마트.
#
# [returning_users 재정의, 2026-07-09] 기존 산식 "(first_visit 없는 유저수) −
# (first_visit 있는 유저수)"는 정의가 불명확하고 음수가 나올 수 있었음.
# kpi_dictionary.md의 SSOT 정의("전체 기간 세션 수 > 1인 사용자")로 교체 —
# 사용자별 전체 세션 수를 먼저 구하고, 그중 2회 이상인 사용자가 해당 날짜에
# 관측되면 재방문자로 카운트.
run("dashboard_kpi", f"""
WITH sessions AS (
  SELECT
    event_date,
    user_pseudo_id,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS session_id,
    MAX(is_active_user) AS is_active
  FROM {SRC}
  WHERE event_name = 'session_start'
  GROUP BY 1, 2, 3
),
user_session_counts AS (
  SELECT user_pseudo_id, COUNT(DISTINCT session_id) AS total_sessions
  FROM sessions
  GROUP BY 1
)
SELECT
  e.event_date AS date,
  COUNT(DISTINCT e.user_pseudo_id)                                        AS users,
  COUNT(DISTINCT CONCAT(e.user_pseudo_id, CAST(
    (SELECT value.int_value FROM UNNEST(e.event_params) WHERE key = 'ga_session_id') AS STRING
  )))                                                                     AS sessions,
  COUNTIF(e.event_name = 'page_view')                                     AS page_views,
  ROUND(COUNT(DISTINCT CASE WHEN e.event_name = 'user_engagement'
    THEN CONCAT(e.user_pseudo_id, CAST(
      (SELECT value.int_value FROM UNNEST(e.event_params) WHERE key = 'ga_session_id') AS STRING
    )) END) /
    NULLIF(COUNT(DISTINCT CONCAT(e.user_pseudo_id, CAST(
      (SELECT value.int_value FROM UNNEST(e.event_params) WHERE key = 'ga_session_id') AS STRING
    ))), 0), 2)                                                            AS engagement_rate,
  ROUND(COUNTIF(e.event_name = 'scroll') /
    NULLIF(COUNTIF(e.event_name = 'page_view'), 0), 2)                    AS scroll_rate,
  ROUND(SUM(CASE WHEN e.event_name = 'user_engagement'
    THEN (SELECT value.int_value FROM UNNEST(e.event_params) WHERE key = 'engagement_time_msec') / 1000.0
    ELSE 0 END) / NULLIF(COUNT(DISTINCT e.user_pseudo_id), 0), 0)         AS avg_engagement_time_sec,
  COUNT(DISTINCT CASE WHEN usc.total_sessions > 1 THEN e.user_pseudo_id END) AS returning_users
FROM {SRC} e
LEFT JOIN user_session_counts usc USING (user_pseudo_id)
GROUP BY 1
ORDER BY 1
""")

# ── 2. funnel_mart (커뮤니티 가입 전환 5단계, 순차형) ────────────────
# 방문 → 콘텐츠 소비 → 가입 페이지 도달 → 로그인/가입 시도 → 가입 완료
# (2026-07-09 재설계) 기존 버전은 두 가지 문제가 있었음:
#  1) 각 단계를 독립적으로 COUNT해서 "이전 단계를 거친 사람 중 이번 단계"가
#     아니라 그냥 "이번 이벤트를 겪은 사람" — 진짜 순차 퍼널이 아니었음
#  2) form_start/form_submit 기준이었는데, 실제 /apply 페이지(the-formula-silk.
#     vercel.app)를 확인해보니 카카오/네이버 소셜 로그인 버튼뿐이고 실제
#     <form> 태그가 없어 이 두 이벤트가 애초에 발생하지 않을 가능성이 큼.
#     실 트래픽의 page_view 분포에서 /apply(가입 페이지) → /account(로그인
#     게이트, callbackUrl 파라미터로 보아 NextAuth류 인증 리다이렉트 추정)
#     → /onboarding(가입 직후 전용 안내 페이지로 추정) 경로를 대신 사용.
#     이 세 경로의 실제 의미는 서비스 담당자 확인이 필요한 추정치임.
run("funnel_mart", f"""
WITH user_steps AS (
  SELECT
    user_pseudo_id,
    LOGICAL_OR(event_name = 'session_start') AS step1,
    LOGICAL_OR(event_name = 'scroll') AS has_scroll,
    LOGICAL_OR(event_name = 'page_view') AS has_pageview,
    LOGICAL_OR(event_name = 'page_view' AND REGEXP_CONTAINS(
      (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'page_location'), r'/apply'
    )) AS reached3_raw,
    LOGICAL_OR(event_name = 'page_view' AND REGEXP_CONTAINS(
      (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'page_location'), r'/account'
    )) AS reached4_raw,
    LOGICAL_OR(event_name = 'page_view' AND REGEXP_CONTAINS(
      (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'page_location'), r'/onboarding'
    )) AS reached5_raw
  FROM {SRC}
  GROUP BY user_pseudo_id
),
cumulative AS (
  SELECT
    step1 AS s1,
    step1 AND has_scroll AND has_pageview AS s2,  -- 콘텐츠 소비: page_view + scroll 둘 다
    step1 AND has_scroll AND has_pageview AND reached3_raw AS s3,
    step1 AND has_scroll AND has_pageview AND reached3_raw AND reached4_raw AS s4,
    step1 AND has_scroll AND has_pageview AND reached3_raw AND reached4_raw AND reached5_raw AS s5
  FROM user_steps
),
steps AS (
  SELECT '방문' AS funnel_step, 1 AS step_order, COUNTIF(s1) AS users FROM cumulative
  UNION ALL
  SELECT '콘텐츠 소비', 2, COUNTIF(s2) FROM cumulative
  UNION ALL
  SELECT '가입 페이지 도달', 3, COUNTIF(s3) FROM cumulative
  UNION ALL
  SELECT '로그인/가입 시도', 4, COUNTIF(s4) FROM cumulative
  UNION ALL
  SELECT '가입 완료', 5, COUNTIF(s5) FROM cumulative
)
SELECT
  funnel_step,
  step_order,
  users,
  ROUND(1 - users / NULLIF(LAG(users) OVER (ORDER BY step_order), 0), 3) AS drop_off_rate
  -- LAG(users): 바로 이전 단계의 인원수를 가져와 "이전 단계 대비 몇 % 이탈했는지" 계산
  -- NULLIF(...,0): 이전 단계가 0명이면 나눗셈 에러 대신 NULL 처리
FROM steps
ORDER BY step_order
""")

# ── 3. marketing_channel_mart ─────────────────────────────────────────
# 유입 채널(자연검색/유료검색/소셜/추천/이메일/직접)별 세션·참여율 집계.
# GA4의 raw traffic_source.medium 값을 사람이 이해하는 채널 그룹으로 매핑(CASE WHEN)하는 게 핵심.
run("marketing_channel_mart", f"""
WITH session_channel AS (
  SELECT
    user_pseudo_id,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS session_id,
    CASE
      WHEN traffic_source.medium = 'organic'                        THEN 'Organic Search'
      WHEN traffic_source.medium IN ('cpc', 'paidsearch', 'paid')  THEN 'Paid Search'
      WHEN traffic_source.medium IN ('social', 'social-network')   THEN 'Social'
      WHEN traffic_source.medium = 'referral'                      THEN 'Referral'
      WHEN traffic_source.medium = 'email'                         THEN 'Email'
      ELSE 'Direct'
    END AS channel_group,
    MAX(CASE WHEN event_name = 'user_engagement' THEN 1 ELSE 0 END) AS is_engaged
  FROM {SRC}
  WHERE event_name = 'session_start'
  GROUP BY 1, 2, 3
)
SELECT
  channel_group,
  COUNT(DISTINCT CONCAT(user_pseudo_id, CAST(session_id AS STRING))) AS sessions,
  COUNT(DISTINCT user_pseudo_id)                                      AS users,
  ROUND(AVG(is_engaged), 2)                                          AS engagement_rate
FROM session_channel
GROUP BY 1
ORDER BY sessions DESC
""")

# ── 4. landing_page_mart ──────────────────────────────────────────────
# 페이지별 조회수/스크롤율/평균 체류시간. HAVING page_views >= 3으로
# 노이즈성 저빈도 페이지(오타 URL 등)를 걸러낸다.
run("landing_page_mart", f"""
WITH page_events AS (
  SELECT
    REGEXP_EXTRACT(
      (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'page_location'),
      r'https?://[^/]+(.*)'
    ) AS page_path,
    event_name,
    user_pseudo_id,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'engagement_time_msec') AS eng_ms
  FROM {SRC}
  WHERE event_name IN ('page_view', 'scroll', 'user_engagement')
)
SELECT
  IFNULL(page_path, '/')                              AS page_path,
  COUNTIF(event_name = 'page_view')                  AS page_views,
  ROUND(COUNTIF(event_name = 'scroll') /
    NULLIF(COUNTIF(event_name = 'page_view'), 0), 2) AS scroll_rate,
  ROUND(SUM(CASE WHEN event_name = 'user_engagement'
    THEN eng_ms / 1000.0 ELSE 0 END) /
    NULLIF(COUNT(DISTINCT user_pseudo_id), 0), 0)    AS avg_engagement_time_sec
FROM page_events
GROUP BY 1
HAVING page_views >= 3
ORDER BY page_views DESC
""")

# ── 5. journey_mart ───────────────────────────────────────────────────
# 세션별 페이지 방문 순서를 "A → B → C" 문자열로 이어붙여, 사용자가 실제로
# 어떤 경로를 타고 이동하는지 보여준다. ARRAY_AGG(... ORDER BY step)이 핵심.
#
# [집계 버그 수정, 2026-07-09] 기존엔 GROUP BY user_pseudo_id, session_id로
# 끝나서 "경로별 세션 수"가 아니라 "세션 1건당 1행"이 나왔음(같은 경로를 밟은
# 여러 세션이 안 합쳐짐). session_paths CTE에서 세션별 경로 문자열을 먼저
# 만든 뒤, 바깥에서 path로 다시 GROUP BY해서 "가장 흔한 경로 TOP N"이 되도록
# 한 겹 더 집계를 추가함.
run("journey_mart", f"""
WITH page_sequence AS (
  SELECT
    user_pseudo_id,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS session_id,
    REGEXP_EXTRACT(
      (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'page_location'),
      r'https?://[^/]+(.*)'
    ) AS page_path,
    ROW_NUMBER() OVER (
      PARTITION BY user_pseudo_id,
        (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id')
      ORDER BY event_timestamp
    ) AS step
  FROM {SRC}
  WHERE event_name = 'page_view'
),
session_paths AS (
  SELECT
    user_pseudo_id,
    session_id,
    ARRAY_TO_STRING(ARRAY_AGG(IFNULL(page_path, '/') ORDER BY step), ' → ') AS path
  FROM page_sequence
  GROUP BY user_pseudo_id, session_id
)
SELECT
  path,
  COUNT(*) AS sessions
FROM session_paths
GROUP BY path
ORDER BY sessions DESC
LIMIT 200
""")

# ── 6. cohort_mart ────────────────────────────────────────────────────
# 주 단위 코호트 리텐션. 사용자를 "첫 방문 주"(cohort_week)로 그룹핑하고,
# 이후 몇 주째(week_number)까지 돌아오는지를 retention_rate로 계산한다.
# 전형적인 코호트 리텐션 테이블 패턴(first_sessions → weekly_activity → DATE_DIFF로 주차 계산).
run("cohort_mart", f"""
WITH first_sessions AS (
  SELECT user_pseudo_id,
    DATE_TRUNC(MIN(PARSE_DATE('%Y%m%d', event_date)), WEEK) AS cohort_week
  FROM {SRC}
  WHERE event_name = 'first_visit'
  GROUP BY 1
),
weekly_activity AS (
  SELECT DISTINCT user_pseudo_id,
    DATE_TRUNC(PARSE_DATE('%Y%m%d', event_date), WEEK) AS activity_week
  FROM {SRC}
  WHERE event_name = 'session_start'
),
cohort_size AS (
  SELECT cohort_week, COUNT(DISTINCT user_pseudo_id) AS total_users
  FROM first_sessions GROUP BY 1
),
raw AS (
  SELECT
    f.cohort_week,
    DATE_DIFF(a.activity_week, f.cohort_week, WEEK) AS week_number,
    COUNT(DISTINCT f.user_pseudo_id) AS users
  FROM first_sessions f
  JOIN weekly_activity a USING (user_pseudo_id)
  WHERE a.activity_week >= f.cohort_week
  GROUP BY 1, 2
)
SELECT
  r.cohort_week,
  r.week_number,
  r.users,
  ROUND(r.users / NULLIF(cs.total_users, 0), 2) AS retention_rate
FROM raw r
JOIN cohort_size cs USING (cohort_week)
ORDER BY 1, 2
""")

# ── 7. recommendation_mart ─────────────────────────────────────────────
# 해시태그 기반 관련 글 추천 기능(2026-07-09 설계, 별도 프론트엔드 배포 예정)의
# 노출/클릭 성과. recommendation_shown/recommendation_click 커스텀 이벤트가
# 아직 실제로 발생한 적 없어(기능 미배포) 지금은 0행이 정상이며, 기능 배포 후
# 이 VIEW를 따로 재실행할 필요 없이 조회 시점에 자동으로 채워진다.
run("recommendation_mart", f"""
WITH rec_events AS (
  SELECT
    event_name,
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'article_id') AS article_id
  FROM {SRC}
  WHERE event_name IN ('recommendation_shown', 'recommendation_click')
)
SELECT
  article_id,
  COUNTIF(event_name = 'recommendation_shown') AS shown,
  COUNTIF(event_name = 'recommendation_click') AS clicked,
  ROUND(SAFE_DIVIDE(
    COUNTIF(event_name = 'recommendation_click'),
    COUNTIF(event_name = 'recommendation_shown')
  ), 3) AS click_through_rate
FROM rec_events
GROUP BY article_id
ORDER BY shown DESC
""")

print("\n완료.")
