# 홈 피드 기본 정렬(최신순 vs 인기순) A/B 실험 마트 — 목업 데이터 생성 스크립트
#
# [역할] "신규 방문자에게 홈(/) 기본 정렬을 최신순(A, 현행) 대신 인기순(B)으로
# 보여주면 아티클 클릭률이 오르는가"를 검증하기 위한 실험 설계를 스키마로 옮긴 것.
#
# 실제 middleware.ts 리다이렉트 로직(사용자를 A/B로 나눠 배정)이 아직 사이트에
# 배포되지 않아 진짜 이벤트 데이터가 없으므로, signup_prompt_experiment_mart와
# 동일하게 파이썬으로 그럴듯한 목업 행을 만들어 TABLE로 적재한다. 실제 배포 후
# GA4 page_location의 sort=popular 유무로 집계하는 실데이터 VIEW로 교체해야 한다.
import os
import random
from dotenv import load_dotenv
from google.cloud import bigquery

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

PROJECT = os.environ.get("GCP_PROJECT_ID", "gen-lang-client-0891732976")
DATASET = "formula_silk_analytics"
TABLE = "home_sort_experiment_mart"

SCHEMA = [
    bigquery.SchemaField("date", "DATE"),
    bigquery.SchemaField("variant", "STRING"),  # 'A' (최신순, 현행) / 'B' (인기순)
    bigquery.SchemaField("sessions", "INTEGER"),                 # 홈 진입 세션 (분모)
    bigquery.SchemaField("article_click_sessions", "INTEGER"),   # /article/*로 이어진 세션 (분자, Primary)
    bigquery.SchemaField("bounced_sessions", "INTEGER"),          # 홈만 보고 나간 세션 (Guardrail)
]

DATES = [f"2026-07-{d:02d}" for d in range(1, 15)]  # 2주치 목업


def make_mock_rows():
    """A(최신순)는 베이스라인, B(인기순)는 가설대로 아티클 클릭률이 소폭 높게,
    이탈률(Guardrail)은 A와 비슷한 수준(정렬 변경이 이탈을 악화시키지 않음)으로 생성."""
    random.seed(42)  # 재현 가능하도록 고정 시드
    rows = []
    for date in DATES:
        for variant in ("A", "B"):
            sessions = random.randint(10, 25)  # 실데이터 홈 트래픽 규모(11일 258회)에 맞춘 소규모 값
            if variant == "A":
                click_rate = random.uniform(0.30, 0.45)
                bounce_rate = random.uniform(0.35, 0.45)
            else:
                click_rate = random.uniform(0.40, 0.55)
                bounce_rate = random.uniform(0.33, 0.43)
            rows.append({
                "date": date,
                "variant": variant,
                "sessions": sessions,
                "article_click_sessions": round(sessions * click_rate),
                "bounced_sessions": round(sessions * bounce_rate),
            })
    return rows


def main():
    client = bigquery.Client(project=PROJECT)
    table_ref = f"{PROJECT}.{DATASET}.{TABLE}"

    client.query(f"DROP TABLE IF EXISTS `{table_ref}`").result()
    table = bigquery.Table(table_ref, schema=SCHEMA)
    client.create_table(table)

    rows = make_mock_rows()
    errors = client.insert_rows_json(table_ref, rows)
    if errors:
        raise RuntimeError(f"적재 실패: {errors}")

    print(f"{TABLE}: 목업 {len(rows)}행 적재 완료 (middleware 리다이렉트 배포 전까지 임시 데이터)")


if __name__ == "__main__":
    main()
