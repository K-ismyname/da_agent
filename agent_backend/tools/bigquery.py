# BigQuery Mart 조회 툴 — 에이전트가 직접 호출
#
# [역할]
# LangChain @tool로 감싼 함수들 = LLM이 "이 도구를 호출하겠다"고 판단하면
# 실제로 실행되어 결과를 다시 LLM에게 돌려주는 함수. agents/nodes.py의
# _invoke_with_tools()가 이 함수들을 LLM에 바인딩해서 쓴다.
#
# [왜 이렇게 설계했나]
# - CLAUDE.md 원칙 "Mart only / No Raw table access"를 코드 레벨에서 강제하기 위해
#   MART_TABLES 화이트리스트를 두고, 여기 없는 테이블명은 쿼리 자체가 안 나가게 막았다.
#   (LLM이 프롬프트만으로 "Raw 테이블 쓰지마"를 지키게 하는 건 불안정하므로,
#    실제 실행 계층에서 한 번 더 검증하는 이중 방어)
# - BigQuery Client는 연결 비용이 커서 모듈 전역에 한 번만 생성(싱글톤)하고 재사용한다.
import os
from langchain_core.tools import tool
from google.cloud import bigquery

DATASET = "formula_silk_analytics"
_client: bigquery.Client | None = None

def _get_client() -> bigquery.Client:
    """BigQuery 클라이언트 지연 생성(lazy init). 최초 호출 시에만 실제 연결을 만들고,
    이후 호출은 전역 _client를 재사용해 매번 연결 비용을 내지 않는다."""
    global _client
    if _client is None:
        _client = bigquery.Client()
    return _client

# 에이전트가 접근 가능한 마트 화이트리스트.
# CLAUDE.md의 "Raw events_* 직접 접근 금지"를 코드로 강제하는 지점 —
# 이 set에 없는 테이블명은 아래 query_mart/get_date_range에서 즉시 거부된다.
MART_TABLES = {
    "dashboard_kpi", "funnel_mart", "marketing_channel_mart",
    "landing_page_mart", "journey_mart", "cohort_mart", "ab_test_mart",
    "recommendation_mart", "signup_prompt_experiment_mart",
    "home_sort_experiment_mart", "search_query_mart"
}

@tool
def query_mart(table_name: str) -> str:
    """Query a BigQuery Mart table. table_name must be exactly one of:
    - dashboard_kpi: 일자별 사용자/세션/PV/참여율/재방문
    - funnel_mart: 가입 전환 퍼널 단계별 이탈률 (cohort_date별 = 첫 방문일 코호트, 날짜별 추세 비교 가능)
    - marketing_channel_mart: 유입 채널별 세션 (date별, 날짜별 추세 비교 가능; 신뢰도 LOW — UTM 미설정)
    - landing_page_mart: 페이지별 조회수/스크롤/체류 (date별, 날짜별 추세 비교 가능)
    - journey_mart: 세션 이동 경로
    - cohort_mart: 주차별 리텐션
    - recommendation_mart: 관련 글 추천 노출/클릭률
    - search_query_mart: 사이트 내 검색어와 콘텐츠 갭 (no_click_rate 높을수록 갭)
    - signup_prompt_experiment_mart / home_sort_experiment_mart: A/B 실험 원자료
    - ab_test_mart: ⚠️ 무관한 Meta Ads 데모 (사용 금지)"""
    # 독스트링이 곧 LLM에게 주는 도구 사용 설명서 — 여기 적힌 그대로 LLM이 읽고 판단한다.
    if table_name not in MART_TABLES:
        return f"ERROR: {table_name} is not a valid mart table."  # 화이트리스트 방어: 잘못된 테이블명은 쿼리 없이 즉시 에러 반환
    project = os.environ.get("GCP_PROJECT_ID", "")
    query = f"SELECT * FROM `{project}.{DATASET}.{table_name}` LIMIT 500"  # LIMIT 500: 원본 전체를 다 가져오지 않고 샘플만 — 토큰/비용 절약
    rows = _get_client().query(query).result()
    return str([dict(row) for row in rows])  # LLM은 텍스트만 이해하므로 리스트를 문자열로 직렬화해서 반환

@tool
def get_ab_test_summary(start_date: str = "", end_date: str = "") -> str:
    """Get aggregated A/B test metrics per variant from ab_test_mart.
    Returns per-variant totals (spend, clicks, impressions, sessions, engaged_sessions,
    add_to_carts, checkouts, purchases, revenue) plus derived Primary metrics
    (CVR, ROAS, cost_per_purchase) and Guardrail metrics (CPC, CPM, cost_per_atc).
    Dates optional, format YYYY-MM-DD.
    ⚠️ ab_test_mart is a synthetic Meta Ads study dataset UNRELATED to this
    community (no real ads run) — use get_signup_experiment_summary for this
    community's actual signup-prompt banner experiment instead."""
    # 왜 SQL에서 집계를 다 끝내나: LLM에게 원본 행을 주고 "평균 내봐"라고 시키면
    # 계산 실수(환각)가 날 수 있다. CVR/ROAS 같은 핵심 지표는 SQL이 결정론적으로
    # 계산해서 "완성된 숫자"만 LLM에 넘긴다 — CLAUDE.md의 "KPI SSOT" 원칙 실행부.
    project = os.environ.get("GCP_PROJECT_ID", "")
    where = ""
    if start_date and end_date:
        where = f"WHERE date BETWEEN '{start_date}' AND '{end_date}'"
    query = f"""
        SELECT
          ab_variant,
          MIN(date) AS start_date, MAX(date) AS end_date,
          SUM(impressions) AS impressions, SUM(clicks) AS clicks,
          ROUND(SUM(spend), 2) AS spend,
          SUM(sessions) AS sessions, SUM(engaged_sessions) AS engaged_sessions,
          SUM(add_to_carts) AS add_to_carts, SUM(checkouts) AS checkouts,
          SUM(purchases) AS purchases, ROUND(SUM(revenue), 2) AS revenue,
          ROUND(SAFE_DIVIDE(SUM(purchases), SUM(sessions)) * 100, 2) AS cvr_pct,
          ROUND(SAFE_DIVIDE(SUM(revenue), SUM(spend)), 2) AS roas,
          ROUND(SAFE_DIVIDE(SUM(spend), SUM(purchases)), 2) AS cost_per_purchase,
          ROUND(SAFE_DIVIDE(SUM(spend), SUM(clicks)), 2) AS cpc,
          ROUND(SAFE_DIVIDE(SUM(spend), SUM(impressions)) * 1000, 2) AS cpm,
          ROUND(SAFE_DIVIDE(SUM(spend), SUM(add_to_carts)), 2) AS cost_per_atc
          -- SAFE_DIVIDE: 분모가 0이면 에러 대신 NULL 반환.
          -- 과거 버그(관찰기록 1390) — 세션/클릭이 0인 구간에서 일반 나눗셈 쓰다가
          -- 쿼리 자체가 크래시난 적이 있어 전 지표에 일괄 적용함.
        FROM `{project}.{DATASET}.ab_test_mart`
        {where}
        GROUP BY ab_variant ORDER BY ab_variant
    """
    rows = _get_client().query(query).result()
    return str([dict(row) for row in rows])


# 실험별 마트/컬럼/설명 매핑. run_significance_test와 get_experiment_summary가
# 이 화이트리스트에 있는 experiment 이름만 받도록 해서, LLM이 임의 테이블명·
# 컬럼명을 SQL에 직접 흘려넣지 못하게 막는다(MART_TABLES와 같은 이중 방어 원칙).
# "real": True인 항목만 실제 커뮤니티 실험 — Data Scientist가 질문에 맞춰
# 이 중 하나를 골라야 한다(description을 프롬프트에 그대로 노출).
EXPERIMENT_METRICS = {
    # ⚠️ 커뮤니티와 무관한 데모용. ab_test_mart는 실제 집행한 광고가 아니라
    # Meta Ads×GA4 스터디 노트(JU_DATA)의 이커머스 예제를 그대로 가져온 합성
    # 데이터라, spend/CPC/CPM/add_to_carts 같은 지표 자체가 광고를 안 하고
    # 장바구니도 없는 이 커뮤니티에는 맞지 않는다. z-test 코드 재사용성을
    # 보여주는 용도로만 남겨둔 항목 — 실제 성과로 발표하면 안 됨.
    "ab_test": {
        "table": "ab_test_mart",
        "variant_col": "ab_variant",
        "numerator_col": "purchases",
        "denominator_col": "sessions",
        "guardrail_col": None,
        "description": "⚠️ 무관한 데모(Meta Ads 스터디 자료) — 실제 커뮤니티 실험 아님, 분석에 쓰지 말 것",
        "real": False,
    },
    # 실제 커뮤니티 실험. 가입 유도 배너를 스크롤 시점에 능동적으로 노출(B)했을 때
    # 수동 노출(A)보다 /apply 도달률이 오르는지 검증 — 광고비·장바구니 없이
    # 순수 페이지 도달 비율만 비교하므로 이 서비스에 실제로 적용 가능한 설계.
    "signup_prompt": {
        "table": "signup_prompt_experiment_mart",
        "variant_col": "variant",
        "numerator_col": "apply_reached",
        "denominator_col": "users_exposed",
        "guardrail_col": "bounced",  # 분모는 denominator_col과 동일(users_exposed)
        "description": "가입 유도 배너: 수동 노출(A, 저장/댓글/팔로우 시도 시) vs 스크롤 90% 시점 능동 노출(B). Primary=가입 페이지 도달률, Guardrail=이탈률",
        "real": True,
    },
    # 실제 커뮤니티 실험. 홈(/) 신규 방문자에게 기본 정렬을 최신순(A, 현행)
    # 대신 인기순(B)으로 배정했을 때 아티클 클릭률이 오르는지 검증.
    "home_sort": {
        "table": "home_sort_experiment_mart",
        "variant_col": "variant",
        "numerator_col": "article_click_sessions",
        "denominator_col": "sessions",
        "guardrail_col": "bounced_sessions",  # 분모는 denominator_col과 동일(sessions)
        "description": "홈 피드 기본 정렬: 최신순(A, 현행) vs 인기순(B). Primary=아티클 클릭률, Guardrail=이탈률",
        "real": True,
    },
}


@tool
def get_experiment_summary(experiment: str, start_date: str = "", end_date: str = "") -> str:
    """Get aggregated Primary/Guardrail metrics per variant for a named experiment.
    experiment must be one of the REGISTERED experiments — call this with the
    experiment name that matches the question (see each experiment's description
    in your system prompt). Returns per-variant totals, Primary rate
    (numerator/denominator), and Guardrail rate (guardrail_col/denominator) if
    the experiment has one. Dates optional, format YYYY-MM-DD.
    This is the SSOT evidence for A/B analysis — do NOT use ab_test_mart's
    ad/e-commerce metrics for this community's real experiments."""
    # 왜 SQL에서 집계를 다 끝내나: LLM에게 원본 행을 주고 "평균 내봐"라고 시키면
    # 계산 실수(환각)가 날 수 있다. Primary/Guardrail 비율은 SQL이 결정론적으로
    # 계산해서 "완성된 숫자"만 LLM에 넘긴다 — CLAUDE.md의 "KPI SSOT" 원칙 실행부.
    if experiment not in EXPERIMENT_METRICS:
        return f"ERROR: unknown experiment '{experiment}'. Valid: {list(EXPERIMENT_METRICS)}"
    cfg = EXPERIMENT_METRICS[experiment]
    project = os.environ.get("GCP_PROJECT_ID", "")
    where = ""
    if start_date and end_date:
        where = f"WHERE date BETWEEN '{start_date}' AND '{end_date}'"
    guardrail_select = ""
    if cfg["guardrail_col"]:
        guardrail_select = f"""
          , SUM({cfg['guardrail_col']}) AS guardrail_count
          , ROUND(SAFE_DIVIDE(SUM({cfg['guardrail_col']}), SUM({cfg['denominator_col']})) * 100, 2) AS guardrail_rate_pct"""
    query = f"""
        SELECT
          {cfg['variant_col']} AS variant,
          MIN(date) AS start_date, MAX(date) AS end_date,
          SUM({cfg['numerator_col']}) AS numerator_count,
          SUM({cfg['denominator_col']}) AS denominator_count,
          ROUND(SAFE_DIVIDE(SUM({cfg['numerator_col']}), SUM({cfg['denominator_col']})) * 100, 2) AS primary_rate_pct
          -- SAFE_DIVIDE: 분모가 0이면 에러 대신 NULL 반환 (과거 버그, 관찰기록 1390).
          {guardrail_select}
        FROM `{project}.{DATASET}.{cfg['table']}`
        {where}
        GROUP BY variant ORDER BY variant
    """
    rows = _get_client().query(query).result()
    return str([dict(row) for row in rows])


@tool
def run_significance_test(experiment: str, start_date: str = "", end_date: str = "") -> str:
    """Run a two-proportion z-test between variant A and B for a named experiment.
    experiment must match a REGISTERED experiment (see descriptions in your system
    prompt) — pick the one that matches the question, never guess a table/column
    directly. Returns z-statistic and p-value computed deterministically in Python.
    ALWAYS use this instead of estimating p-values."""
    # 왜 p-value를 LLM이 아니라 여기서 계산하나: LLM은 통계 검정 수치를 "그럴듯하게
    # 추정"할 뿐 실제 계산이 아니라서 틀릴 수 있다. 독스트링에 "ALWAYS use this
    # instead of estimating"이라고 못박아, LLM이 스스로 p-value를 만들어내지 못하게 함.
    import math
    if experiment not in EXPERIMENT_METRICS:
        return f"ERROR: unknown experiment '{experiment}'. Valid: {list(EXPERIMENT_METRICS)}"
    cfg = EXPERIMENT_METRICS[experiment]
    project = os.environ.get("GCP_PROJECT_ID", "")
    where = ""
    if start_date and end_date:
        where = f"WHERE date BETWEEN '{start_date}' AND '{end_date}'"
    query = f"""
        SELECT {cfg['variant_col']} AS variant,
          SUM({cfg['numerator_col']}) AS x, SUM({cfg['denominator_col']}) AS n
        FROM `{project}.{DATASET}.{cfg['table']}` {where}
        GROUP BY variant ORDER BY variant
    """
    rows = [dict(r) for r in _get_client().query(query).result()]
    if len(rows) != 2:
        return f"ERROR: expected 2 variants, got {len(rows)}"  # A/B 정확히 2개 변형 전제 — 3개 이상이면 이 z-test 자체가 성립 안 함
    (x1, n1), (x2, n2) = (rows[0]["x"], rows[0]["n"]), (rows[1]["x"], rows[1]["n"])
    if not n1 or not n2:
        return f"ERROR: zero denominator in a variant (A={n1}, B={n2}) — cannot run z-test"
        # 과거 버그(관찰기록 1393): 분모가 0인 변형이 있으면 아래 나눗셈(x1/n1)에서
        # ZeroDivisionError로 파이프라인 전체가 죽었음 — 여기서 미리 걸러 에러 문자열로 반환
    p1, p2 = x1 / n1, x2 / n2                                    # 변형별 실제 전환율
    p_pool = (x1 + x2) / (n1 + n2)                                # 두 그룹을 합친 전체 전환율 (귀무가설: 두 그룹 전환율이 같다는 가정하의 공통 비율)
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))    # 표준오차(Standard Error) — 표준 two-proportion z-test 공식 그대로
    z = (p2 - p1) / se if se else 0.0                             # z 통계량 = (차이) / (표준오차)
    p_value = math.erfc(abs(z) / math.sqrt(2))  # two-tailed     # 정규분포 양측검정 p-value. erfc(상보오차함수)로 정규분포 CDF를 근사 없이 계산
    return str({
        "a": {"variant": rows[0]["variant"], cfg["numerator_col"]: x1, cfg["denominator_col"]: n1, "rate_pct": round(p1 * 100, 3)},
        "b": {"variant": rows[1]["variant"], cfg["numerator_col"]: x2, cfg["denominator_col"]: n2, "rate_pct": round(p2 * 100, 3)},
        "z_statistic": round(z, 3),
        "p_value": round(p_value, 6),
        "significant_at_95": p_value < 0.05,
    })


# 테이블별 날짜 컬럼 — 없는 테이블은 기간 개념이 없음 (스냅샷 집계)
# 왜 딕셔너리로 관리하나: 마트마다 날짜 컬럼명이 다르고(date vs cohort_week vs
# cohort_date), 아예 없는 마트도 있어서(journey/recommendation) 하드코딩 매핑이 필요.
DATE_COLUMNS = {
    "dashboard_kpi": "date",
    "ab_test_mart": "date",
    "cohort_mart": "cohort_week",
    "funnel_mart": "cohort_date",        # 첫 방문일 코호트별 퍼널
    "marketing_channel_mart": "date",
    "landing_page_mart": "date",
    "signup_prompt_experiment_mart": "date",
    "home_sort_experiment_mart": "date",
}


@tool
def get_date_range(table_name: str) -> str:
    """Get the date range available in a mart table.
    Most marts now have a date column (dashboard_kpi, funnel_mart[cohort_date],
    marketing_channel_mart, landing_page_mart, cohort_mart[cohort_week], ab_test_mart,
    signup/home experiment marts); journey_mart and recommendation_mart are snapshots."""
    if table_name not in MART_TABLES:
        return f"ERROR: {table_name} is not a valid mart table."
    col = DATE_COLUMNS.get(table_name)
    if not col:
        return f"INFO: {table_name} has no date column — it is a whole-period snapshot."
    project = os.environ.get("GCP_PROJECT_ID", "")
    query = f"""
        SELECT MIN({col}) as min_date, MAX({col}) as max_date
        FROM `{project}.{DATASET}.{table_name}`
    """
    rows = list(_get_client().query(query).result())
    return str(dict(rows[0])) if rows else "No data"
