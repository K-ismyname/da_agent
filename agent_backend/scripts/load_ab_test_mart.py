# Load Meta Ads + GA4 A/B test CSVs into BigQuery and build ab_test_mart.
# Run once from repo root:
#   GOOGLE_APPLICATION_CREDENTIALS=dashboard/credentials.json python agent_backend/scripts/load_ab_test_mart.py
#
# [역할] build_marts.py가 GA4 raw 이벤트를 VIEW로 실시간 변환하는 것과 달리,
# 이 스크립트는 외부 CSV(자료/ 디렉터리의 Meta Ads 리포트 + GA4 랜딩페이지
# 리포트)를 BigQuery에 적재하고 TABLE(스냅샷)로 굳혀서 ab_test_mart를 만든다.
# CLAUDE.md "A/B Test Analysis: 자료/*.csv → load_ab_test_mart.py로 적재"가
# 이 파일이다.
#
# [왜 VIEW가 아니라 TABLE인가] A/B 테스트는 정해진 실험 기간의 결과를
# 분석하는 것이라, GA4 마트들처럼 "항상 최신"일 필요가 없다. 오히려 실험
# 기간 중간에 원본 CSV가 바뀌면 안 되므로, 한 번 적재한 스냅샷을 고정해
# 분석 재현성을 지키는 게 더 중요해 TABLE로 만든다(관찰기록 1128, 1154).
import os
import pandas as pd
from google.cloud import bigquery

PROJECT = os.environ.get("GCP_PROJECT_ID", "gen-lang-client-0891732976")
DATASET = "formula_silk_analytics"
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "자료")

MART_SQL = f"""
CREATE OR REPLACE TABLE `{PROJECT}.{DATASET}.ab_test_mart` AS
-- meta(광고 성과)와 ga4(실제 전환) 두 소스를 join_key로 결합.
-- join_key는 CSV 적재 시점에 이미 "날짜+변형" 조합으로 부여된 조인 키로 추정
-- (원본 CSV 컬럼 그대로 사용 — 이 스크립트에서 새로 생성하지 않음).
WITH meta AS (
  SELECT
    join_key,
    MIN(date_start)                    AS date,
    MIN(ab_variant)                    AS ab_variant,
    SUM(impressions)                   AS impressions,
    SUM(inline_link_clicks)            AS clicks,
    SUM(spend)                         AS spend,
    SUM(purchase)                      AS meta_purchases,
    SUM(add_to_cart)                   AS meta_add_to_cart,
    SUM(purchase_conversion_value)     AS meta_revenue
  FROM `{PROJECT}.{DATASET}.meta_ads_src`
  GROUP BY join_key
),
ga4 AS (
  SELECT
    join_key,
    SUM(sessions)                      AS sessions,
    SUM(engagedSessions)               AS engaged_sessions,
    SUM(addToCarts)                    AS add_to_carts,
    SUM(checkouts)                     AS checkouts,
    SUM(ecommercePurchases)            AS purchases,
    SUM(totalRevenue)                  AS revenue
  FROM `{PROJECT}.{DATASET}.ga4_landing_src`
  GROUP BY join_key
)
SELECT
  m.date,
  m.ab_variant,
  SUM(m.impressions)        AS impressions,
  SUM(m.clicks)             AS clicks,
  ROUND(SUM(m.spend), 2)    AS spend,
  SUM(m.meta_purchases)     AS meta_purchases,
  SUM(m.meta_add_to_cart)   AS meta_add_to_cart,
  ROUND(SUM(m.meta_revenue), 2) AS meta_revenue,
  SUM(g.sessions)           AS sessions,
  SUM(g.engaged_sessions)   AS engaged_sessions,
  SUM(g.add_to_carts)       AS add_to_carts,
  SUM(g.checkouts)          AS checkouts,
  SUM(g.purchases)          AS purchases,
  ROUND(SUM(g.revenue), 2)  AS revenue
FROM meta m
LEFT JOIN ga4 g USING (join_key)
-- LEFT JOIN(INNER 아님): Meta 광고는 노출/클릭이 있었는데 GA4 전환 데이터가
-- 그 시점에 없을 수 있음(세션이 0인 날 등) — 이런 행도 광고비 집계에서
-- 누락되면 안 되므로 GA4 쪽이 없어도 Meta 행은 항상 남긴다.
GROUP BY m.date, m.ab_variant
ORDER BY m.date, m.ab_variant
"""

VERIFY_SQL = f"""
SELECT
  ab_variant,
  ROUND(SUM(purchases) / SUM(sessions) * 100, 2)  AS cvr_pct,
  ROUND(SUM(revenue) / SUM(spend), 2)             AS roas,
  ROUND(SUM(spend) / SUM(clicks), 2)              AS cpc,
  ROUND(SUM(spend) / SUM(purchases), 2)           AS cost_per_purchase,
  ROUND(SUM(spend) / SUM(add_to_carts), 2)        AS cost_per_atc
FROM `{PROJECT}.{DATASET}.ab_test_mart`
GROUP BY ab_variant ORDER BY ab_variant
"""


def main():
    """CSV 적재(1~2단계) → 마트 생성(3단계) → 검증 출력(4단계)의 4스텝 배치.
    한 번 실행하고 끝나는 스크립트라 함수형 분리 없이 순서대로 나열했다."""
    client = bigquery.Client(project=PROJECT)

    # 1) Meta Ads source (drop JSON action columns — scalars already extracted)
    # actions/action_values 등은 원본 CSV에 JSON 배열로 들어있는데, 이미 필요한
    # 값(purchase, add_to_cart 등)은 별도 스칼라 컬럼으로 추출되어 있어 중복 제거
    meta = pd.read_csv(os.path.join(DATA_DIR, "meta_ads_data.csv"))
    meta = meta.drop(columns=["actions", "action_values", "purchase_roas", "cost_per_action_type"], errors="ignore")
    meta["date_start"] = pd.to_datetime(meta["date_start"]).dt.date
    meta["date_stop"] = pd.to_datetime(meta["date_stop"]).dt.date

    # 2) GA4 landing source
    ga4 = pd.read_csv(os.path.join(DATA_DIR, "ga4_landing_page_data.csv"))
    ga4["date"] = pd.to_datetime(ga4["date"], format="%Y%m%d").dt.date  # GA4 export 특유의 YYYYMMDD 정수형 날짜 포맷 파싱

    # WRITE_TRUNCATE: 재실행 시 기존 데이터를 지우고 새로 채움 — 이 스크립트를
    # 여러 번 돌려도(예: CSV 갱신 후 재적재) 중복 행이 쌓이지 않도록 함
    cfg = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
    for name, df in [("meta_ads_src", meta), ("ga4_landing_src", ga4)]:
        job = client.load_table_from_dataframe(df, f"{PROJECT}.{DATASET}.{name}", job_config=cfg)
        job.result()
        print(f"loaded {name}: {len(df)} rows")

    # 3) Build mart
    client.query(MART_SQL).result()
    print("ab_test_mart created")

    # 4) Verify — expected: A cvr 1.19 / cpp 71.94, B cvr 2.21 / cpp 30.92 (full period)
    # 하드코딩된 기대값과 비교하는 자동 검증은 아니고, 사람이 눈으로 대조하는
    # 수동 체크용 출력 — 스크립트가 맞게 동작했는지 실행자가 즉시 확인하게 함
    for row in client.query(VERIFY_SQL).result():
        print(dict(row))


if __name__ == "__main__":
    main()
