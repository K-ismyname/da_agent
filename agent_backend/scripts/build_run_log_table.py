# /analyze 실행 로그 테이블 생성 스크립트 (상시 관측용)
#
# [역할] 매 분석 요청의 질문·경로·결과·검증 점수를 한 행씩 쌓는 run_log 테이블을
# 만든다. main.py가 요청이 끝날 때마다 여기에 insert한다. 이 로그가 쌓이면
# "어떤 질문이 자주 오나 / 어느 게이트에서 자주 막히나 / 환각 위험도 추이"를
# 사후에 분석할 수 있다 — 검증 파이프라인을 실행 순간에만 보는 게 아니라
# 시간축으로 관측(observability)하게 만드는 기반.
#
# 마트(분석 대상 데이터)가 아니라 시스템 자체의 운영 로그이므로 MART_TABLES
# 화이트리스트에는 넣지 않는다(에이전트가 조회할 대상이 아님).
import os
from dotenv import load_dotenv
from google.cloud import bigquery

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

PROJECT = os.environ.get("GCP_PROJECT_ID", "gen-lang-client-0891732976")
DATASET = "formula_silk_analytics"
TABLE = "run_log"

SCHEMA = [
    bigquery.SchemaField("ts", "TIMESTAMP"),            # 실행 시각(UTC)
    bigquery.SchemaField("question", "STRING"),          # 사용자 질문 원문
    bigquery.SchemaField("route", "STRING"),             # nonanalytic / simple / complex
    bigquery.SchemaField("outcome", "STRING"),           # SUCCESS / TRUST_LOW / QA_FAIL / EVAL_FAIL / NONANALYTIC / PIPELINE_ERROR
    bigquery.SchemaField("trust_level", "STRING"),       # Analytics Engineer 판정 (없으면 NULL)
    bigquery.SchemaField("qa_verdict", "STRING"),        # QA Reviewer 판정 (없으면 NULL)
    bigquery.SchemaField("eval_verdict", "STRING"),      # Evaluator 판정 (없으면 NULL)
    bigquery.SchemaField("confidence", "FLOAT"),         # Evaluator confidence (없으면 NULL)
    bigquery.SchemaField("hallucination_risk", "FLOAT"), # Evaluator risk (없으면 NULL)
    bigquery.SchemaField("latency_ms", "INTEGER"),       # 파이프라인 실행 소요(ms)
]


def main():
    client = bigquery.Client(project=PROJECT)
    table_ref = f"{PROJECT}.{DATASET}.{TABLE}"
    table = bigquery.Table(table_ref, schema=SCHEMA)
    # 이미 있으면 그대로 두고(로그 유실 방지), 없을 때만 생성
    table = client.create_table(table, exists_ok=True)
    print(f"{TABLE}: 준비 완료 ({table.table_id}, {len(table.schema)}개 컬럼)")


if __name__ == "__main__":
    main()
