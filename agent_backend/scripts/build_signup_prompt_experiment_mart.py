# 아티클 가입 유도 배너 노출 시점 A/B 실험 마트 — 목업 데이터 생성 스크립트
#
# [역할] "스크롤 90% 도달 시 능동적으로 가입 배너를 띄우는 것(B)이, 지금처럼
# 저장/댓글/팔로우를 시도할 때만 로그인을 유도하는 것(A)보다 /apply 도달률을
# 높이는가"를 검증하기 위한 실험 설계 문서(대화 기록)를 그대로 스키마로 옮긴 것.
#
# 실제 배너 기능(B안)이 아직 사이트에 배포되지 않아 진짜 이벤트 데이터가 없으므로,
# 이 스크립트는 build_marts.py(실데이터 VIEW)나 load_ab_test_mart.py(합성 CSV
# TABLE)와 달리 파이썬으로 직접 그럴듯한 목업 행을 만들어 TABLE로 적재한다.
# 나중에 실제 기능을 배포하고 GA4에 experiment_variant 파라미터가 쌓이기 시작하면,
# 이 스크립트는 버리고 build_marts.py 스타일의 실데이터 VIEW로 교체해야 한다.
import os
import random
from dotenv import load_dotenv
from google.cloud import bigquery

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

PROJECT = os.environ.get("GCP_PROJECT_ID", "gen-lang-client-0891732976")
DATASET = "formula_silk_analytics"
TABLE = "signup_prompt_experiment_mart"

SCHEMA = [
    bigquery.SchemaField("date", "DATE"),
    bigquery.SchemaField("variant", "STRING"),       # 'A' (기존 수동 노출) / 'B' (스크롤 기반 능동 노출)
    bigquery.SchemaField("article_id", "STRING"),
    bigquery.SchemaField("users_exposed", "INTEGER"),  # 트리거 조건(스크롤 90%) 충족 인원
    bigquery.SchemaField("banner_shown", "INTEGER"),   # 배너가 실제 노출된 인원 (A는 항상 0)
    bigquery.SchemaField("banner_click", "INTEGER"),   # 배너 클릭 인원 (A는 항상 0)
    bigquery.SchemaField("apply_reached", "INTEGER"),  # /apply 도달 인원
    bigquery.SchemaField("bounced", "INTEGER"),        # 노출 직후 이탈 인원
]

ARTICLE_IDS = ["seed-post-cn-1", "seed-post-cn-2", "seed-post-cn-3", "seed-post-fm-1"]
DATES = [f"2026-07-{d:02d}" for d in range(1, 15)]  # 2주치 목업


def make_mock_rows():
    """A(수동 노출)는 베이스라인, B(능동 노출)는 가설대로 apply_reached가 소폭 높게,
    동시에 bounced도 약간 높게(배너가 거슬릴 수 있다는 guardrail 리스크) 생성."""
    random.seed(42)  # 재현 가능하도록 고정 시드 — 실행할 때마다 값이 달라지면 목업 검증이 안 됨
    rows = []
    for date in DATES:
        for article_id in ARTICLE_IDS:
            for variant in ("A", "B"):
                exposed = random.randint(15, 40)
                if variant == "A":
                    banner_shown = 0
                    banner_click = 0
                    apply_rate = random.uniform(0.04, 0.07)
                    bounce_rate = random.uniform(0.10, 0.15)
                else:
                    banner_shown = exposed
                    banner_click = round(banner_shown * random.uniform(0.15, 0.25))
                    apply_rate = random.uniform(0.06, 0.10)
                    bounce_rate = random.uniform(0.12, 0.18)
                rows.append({
                    "date": date,
                    "variant": variant,
                    "article_id": article_id,
                    "users_exposed": exposed,
                    "banner_shown": banner_shown,
                    "banner_click": banner_click,
                    "apply_reached": round(exposed * apply_rate),
                    "bounced": round(exposed * bounce_rate),
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

    print(f"{TABLE}: 목업 {len(rows)}행 적재 완료 (실제 기능 배포 전까지 임시 데이터)")


if __name__ == "__main__":
    main()
