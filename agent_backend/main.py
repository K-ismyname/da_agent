# FastAPI 진입점 — LangGraph 파이프라인 실행 및 결과 반환
#
# [역할]
# CLAUDE.md 아키텍처 다이어그램의 "FastAPI + LangGraph" 계층. Next.js 프록시가
# 호출하는 HTTP 엔드포인트를 노출하고, graph.py의 pipeline을 실제로 실행한다.
# 프론트가 필요로 하는 3개 API(/analyze, /data, /ab-test)와 헬스체크(/health)를 제공.
#
# [왜 이렇게 설계했나]
# - 프론트(Next.js)와 백엔드(Python)를 완전히 분리한 이유: LangGraph/LangChain
#   생태계가 Python 중심이라 에이전트 로직은 Python으로 짜는 게 자연스럽고,
#   프론트는 Next.js의 SSR/라우팅 이점을 그대로 쓰기 위함. 두 서버를 HTTP로
#   통신시켜 배포도 독립적으로(Vercel + 별도 Python 서버) 가져갈 수 있다.
# - /analyze(LLM 파이프라인 경유)와 /data, /ab-test(BigQuery 직접 조회) API를
#   분리한 이유: 대시보드에 차트를 그릴 땐 굳이 8개 에이전트를 다 거쳐 LLM
#   비용을 쓸 필요가 없다. "AI 분석이 필요한 질문"과 "이미 정해진 차트 데이터
#   조회"를 분리해 불필요한 LLM 호출을 없앴다(관찰기록 1328 "data API 분리").
import logging
import os
import time
from datetime import datetime, timezone
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Query, Request
from fastapi.responses import JSONResponse
from agent_backend.graph import pipeline
from agent_backend.hooks import run_stop_hooks, send_email
from agent_backend.tools.bigquery import _get_client

load_dotenv()  # .env / .env.local에서 GCP_PROJECT_ID, OPENAI_API_KEY 등 환경변수 로드

logger = logging.getLogger("da_agent")
app = FastAPI(title="DA Agent Backend")

DATASET = "formula_silk_analytics"

# /analyze 결과 캐시 — 같은 질문(q)이 짧은 시간 안에 반복 호출되면 GPT-4o를
# 다시 돌리지 않고 캐시된 응답을 반환한다. 왜 필요한가: 대시보드가 페이지
# 로드마다 자동으로 /analyze를 호출하는데(관찰기록, docs_프로젝트_해부 4번),
# 캐시가 없으면 방문자 1명당 매번 GPT-4o 8회(~$0.27)가 과금된다.
# ponytail: 프로세스 재시작 시 초기화되는 단순 인메모리 dict. 여러 서버
# 인스턴스로 스케일하면 안 맞음 — 그때는 Redis 등 공유 캐시로 교체.
_ANALYZE_CACHE: dict[str, tuple[float, dict]] = {}
ANALYZE_CACHE_TTL_SECONDS = 600

# Next.js 프록시만 호출하도록 공유 시크릿으로 제한 — 미설정 시(로컬 개발) 검사 스킵
# 왜 이런 인증을 뒀나(관찰기록 1432, 1436): 이 백엔드가 공개 인터넷에 노출되면
# 누구나 /analyze를 호출해 OpenAI API 비용을 무제한으로 발생시킬 수 있다.
# Next.js 프록시만 아는 공유 시크릿 헤더를 요구해 직접 호출을 막는다.
BACKEND_SHARED_SECRET = os.environ.get("BACKEND_SHARED_SECRET")


@app.middleware("http")
async def require_shared_secret(request: Request, call_next):
    # /health는 예외 — 배포 플랫폼의 헬스체크가 시크릿을 모르고 호출하기 때문
    if BACKEND_SHARED_SECRET and request.url.path != "/health":
        if request.headers.get("x-backend-secret") != BACKEND_SHARED_SECRET:
            return JSONResponse(status_code=401, content={"error": "UNAUTHORIZED"})
    return await call_next(request)


@app.exception_handler(Exception)
async def unhandled_error(request, exc):
    """BigQuery 장애 등 미처리 예외 → 원인 포함 500 응답."""
    # 왜 전역 핸들러가 필요한가(관찰기록 1395): 이게 없으면 FastAPI가 예외를
    # 그대로 흘려보내 프론트가 파싱 불가능한 에러를 받거나 서버가 스택트레이스를
    # 노출할 위험이 있다. 모든 미처리 예외를 여기서 일관된 JSON 형태로 변환한다.
    logger.exception("unhandled error: %s", request.url.path)
    return JSONResponse(status_code=500, content={"error": "INTERNAL_ERROR", "detail": str(exc)})


def _query(sql: str) -> list[dict]:
    """/data, /ab-test 엔드포인트 전용 — LLM 파이프라인 없이 BigQuery를 직접 조회하는 헬퍼.
    tools/bigquery.py의 _get_client()를 재사용해 커넥션을 이중으로 만들지 않는다."""
    return [dict(r) for r in _get_client().query(sql).result()]


def _outcome(result: dict) -> str:
    """result에서 최종 결과 유형을 결정론적으로 계산 — /analyze의 분기 순서와 동일.
    (로그의 outcome 컬럼값. 실제 응답 분기와 한 곳에서 어긋나지 않도록 같은 순서)."""
    route = result.get("supervisor", {}).get("route", "complex")
    if route == "nonanalytic":
        return "NONANALYTIC"
    if result.get("analytics_engineer", {}).get("trust_level") == "LOW":
        return "TRUST_LOW"
    if result.get("qa_reviewer", {}).get("verdict") == "FAIL":
        return "QA_FAIL"
    if result.get("evaluation", {}).get("verdict") == "FAIL":
        return "EVAL_FAIL"
    return "SUCCESS"


def _log_run(row: dict) -> None:
    """run_log 테이블에 실행 기록 1행 적재 (상시 관측용).
    실패 방어: 로깅이 실패해도 사용자 응답에는 영향 없어야 하므로 예외를 삼킨다.
    background task로 호출돼 응답 지연도 없다."""
    try:
        project = os.environ.get("GCP_PROJECT_ID", "")
        table_ref = f"{project}.{DATASET}.run_log"
        errors = _get_client().insert_rows_json(table_ref, [row])
        if errors:
            logger.warning("run_log insert 부분 실패: %s", errors)
    except Exception:
        logger.warning("run_log insert 실패 (무시)", exc_info=True)


@app.get("/analyze")
async def analyze(
    background: BackgroundTasks,
    q: str = Query(default="이번 달 웹사이트 주요 지표와 이탈 원인을 분석해줘"),
):
    cached = _ANALYZE_CACHE.get(q)
    if cached and time.time() - cached[0] < ANALYZE_CACHE_TTL_SECONDS:
        return cached[1]  # 캐시 히트는 재실행이 아니라 로깅 안 함(원 실행은 이미 기록됨)

    t0 = time.time()

    # AnalysisState의 모든 키를 빈 값으로 미리 채워서 초기 상태를 만듦.
    # 왜 필요한가: LangGraph 노드들이 state["product_analyst"] 처럼 직접 키에
    # 접근하는데, 처음부터 없는 키는 KeyError를 낸다. 모든 키를 빈 dict로
    # 선언해두면 아직 안 채운 키(스킵된 노드 등)도 안전하게 존재한다.
    initial_state = {
        "question": q,
        "supervisor": {},
        "product_analyst": {},
        "analytics_engineer": {},
        "data_scientist": {},
        "qa_reviewer": {},
        "evaluation": {},
        "head_of_data": {},
        "error": None,
    }

    try:
        result = await pipeline.ainvoke(initial_state)  # 비동기 버전(ainvoke) — FastAPI의 async 엔드포인트와 자연스럽게 맞물림
    except Exception as e:
        # 파이프라인 내부(LLM 호출, BigQuery 조회 등)에서 처리 안 된 예외가 나면
        # 여기서 잡아 사용자에게 명확한 에러 코드로 알려줌 (관찰기록 1369)
        logger.exception("pipeline failed")
        background.add_task(_log_run, {
            "ts": datetime.now(timezone.utc).isoformat(),
            "question": q, "route": None, "outcome": "PIPELINE_ERROR",
            "trust_level": None, "qa_verdict": None, "eval_verdict": None,
            "confidence": None, "hallucination_risk": None,
            "latency_ms": int((time.time() - t0) * 1000),
        })
        return JSONResponse(
            status_code=500,
            content={"error": "PIPELINE_ERROR", "detail": str(e)},
        )

    # 실행 로그 1행을 background로 적재 — 어느 분기로 응답하든 한 곳에서만 기록
    # (outcome은 아래 분기와 동일 순서로 _outcome이 계산). 상시 관측용.
    ev = result.get("evaluation", {})
    background.add_task(_log_run, {
        "ts": datetime.now(timezone.utc).isoformat(),
        "question": q,
        "route": result.get("supervisor", {}).get("route"),
        "outcome": _outcome(result),
        "trust_level": result.get("analytics_engineer", {}).get("trust_level"),
        "qa_verdict": result.get("qa_reviewer", {}).get("verdict"),
        "eval_verdict": ev.get("verdict"),
        "confidence": ev.get("confidence"),
        "hallucination_risk": ev.get("hallucination_risk"),
        "latency_ms": int((time.time() - t0) * 1000),
    })

    # Supervisor가 "비분석 질문"으로 판정하면 8개 에이전트가 아무것도 안 돌고
    # 여기로 온다. 억지 분석 대신 Supervisor의 안내 메시지를 그대로 반환한다.
    if result.get("supervisor", {}).get("route") == "nonanalytic":
        return {
            "question": q,
            "route": "nonanalytic",
            "message": result["supervisor"].get("message")
                or "이 시스템은 커뮤니티 웹사이트의 GA4 데이터를 분석해 드립니다. 이탈률·퍼널·코호트·A/B 테스트 등을 질문해 주세요.",
        }

    # graph.py의 Gate에서 "stop"으로 빠지면 result에 evaluation 등이 비어있는
    # 채로 여기까지 온다. 어느 게이트에서 멈췄는지(신뢰도/QA/Eval) 구체적으로 알려준다.
    if result.get("analytics_engineer", {}).get("trust_level") == "LOW":
        return JSONResponse(
            status_code=422,
            content={"error": "DATA_TRUST_LOW", "analytics_engineer": result["analytics_engineer"]},
        )

    if result.get("qa_reviewer", {}).get("verdict") == "FAIL":
        return JSONResponse(
            status_code=422,
            content={"error": "QA_FAIL", "qa": result["qa_reviewer"]},
        )

    if result.get("evaluation", {}).get("verdict") == "FAIL":
        return JSONResponse(
            status_code=422,
            content={"error": "EVAL_FAIL", "evaluation": result["evaluation"]},
        )

    # Stop Hooks: 분석 완료 → report.md → report.pdf → slack (응답 후 백그라운드 실행)
    # 왜 background task로 돌리나: PDF 변환·Slack 전송은 사용자 응답과 무관한
    # 부가 작업이라, 응답을 먼저 반환하고 이후에 비동기로 처리해 응답 속도를 지킨다.
    background.add_task(run_stop_hooks, result)

    # 파이썬 snake_case 키(product_analyst)를 프론트엔드 관례인 camelCase
    # (productAnalyst)로 바꿔서 응답 — 백엔드/프론트 각자의 언어 컨벤션을
    # API 경계에서 변환해주는 지점.
    # simple 경로는 product_analyst/analytics_engineer/qa_reviewer를 스킵하므로
    # 그 칸이 빈 dict로 남는다 — .get()으로 안전하게 꺼낸다.
    response = {
        "question": q,
        "route": result.get("supervisor", {}).get("route", "complex"),
        "pipeline": {
            "productAnalyst": result.get("product_analyst", {}),
            "analyticsEngineer": result.get("analytics_engineer", {}),
            "dataScientist": result.get("data_scientist", {}),
            "qaReviewer": result.get("qa_reviewer", {}),
            "evaluation": result.get("evaluation", {}),
        },
        "brief": result.get("head_of_data", {}),
        "hooks": "scheduled",
        "source": "bigquery",
    }
    _ANALYZE_CACHE[q] = (time.time(), response)
    return response


@app.get("/data")
def get_data():
    """마트 원시 데이터를 직접 반환 — LLM 파이프라인 없이 차트용으로 사용.
    대시보드 첫 진입 시 차트를 그리기 위한 API — /analyze처럼 LLM을 거치지
    않아 비용이 없고 응답도 즉시 온다."""
    project = os.environ.get("GCP_PROJECT_ID", "")
    ds = DATASET
    q = _query
    # funnel/channel/landing 마트는 이제 날짜 차원(cohort_date/date)을 가진다.
    # 대시보드는 전체 스냅샷 형태(단계/채널/페이지당 1행)를 기대하므로 여기서
    # 날짜를 걷어내 다시 집계한다 — 마트에 날짜 차원을 넣으면서도 프론트(page.tsx)를
    # 건드리지 않기 위함. 날짜별 추세는 Data Scientist 에이전트가 query_mart로 직접 조회.
    return {
        "kpi":     q(f"SELECT * FROM `{project}.{ds}.dashboard_kpi` ORDER BY date"),
        "funnel":  q(f"""
            SELECT funnel_step, step_order, SUM(users) AS users,
              ROUND(1 - SUM(users) / NULLIF(LAG(SUM(users)) OVER (ORDER BY step_order), 0), 3) AS drop_off_rate
            FROM `{project}.{ds}.funnel_mart`
            GROUP BY funnel_step, step_order ORDER BY step_order"""),
        "channel": q(f"""
            SELECT channel_group, SUM(sessions) AS sessions, SUM(users) AS users,
              ROUND(AVG(engagement_rate), 2) AS engagement_rate
            FROM `{project}.{ds}.marketing_channel_mart`
            GROUP BY channel_group ORDER BY sessions DESC"""),
        "landing": q(f"""
            SELECT page_path, SUM(page_views) AS page_views,
              ROUND(AVG(scroll_rate), 2) AS scroll_rate,
              ROUND(AVG(avg_engagement_time_sec), 0) AS avg_engagement_time_sec
            FROM `{project}.{ds}.landing_page_mart`
            GROUP BY page_path HAVING page_views >= 3
            ORDER BY page_views DESC LIMIT 10"""),
        "cohort":  q(f"SELECT * FROM `{project}.{ds}.cohort_mart` ORDER BY cohort_week, week_number"),
    }


@app.get("/ab-test")
def get_ab_test():
    """이 커뮤니티의 실제 A/B 테스트(가입 유도 배너) 요약 + 일별 추이 반환.
    이 쿼리는 tools/bigquery.py의 get_signup_experiment_summary()와 SQL이 거의
    동일하다 — 저긴 LLM 에이전트용(문자열 반환), 여긴 /ab-test 페이지 차트용
    (JSON 반환)으로 소비 주체가 달라 별도로 존재한다.
    (2026-07-09) ab_test_mart(무관한 Meta Ads 데모 자료) 대신
    signup_prompt_experiment_mart로 교체 — knowledge/ab_test_framework.md 참고."""
    project = os.environ.get("GCP_PROJECT_ID", "")
    ds = DATASET
    q = _query

    summary = q(f"""
        SELECT variant,
          MIN(date) AS start_date, MAX(date) AS end_date,
          SUM(users_exposed) AS users_exposed,
          SUM(banner_shown) AS banner_shown,
          SUM(banner_click) AS banner_click,
          SUM(apply_reached) AS apply_reached,
          SUM(bounced) AS bounced,
          ROUND(SAFE_DIVIDE(SUM(apply_reached), SUM(users_exposed)) * 100, 2) AS apply_rate_pct,
          ROUND(SAFE_DIVIDE(SUM(bounced), SUM(users_exposed)) * 100, 2) AS bounce_rate_pct,
          ROUND(SAFE_DIVIDE(SUM(banner_click), SUM(banner_shown)) * 100, 2) AS banner_ctr_pct
        FROM `{project}.{ds}.signup_prompt_experiment_mart`
        GROUP BY variant ORDER BY variant
    """)
    daily = q(f"""
        SELECT CAST(date AS STRING) AS date, variant,
          ROUND(SAFE_DIVIDE(SUM(apply_reached), SUM(users_exposed)) * 100, 2) AS apply_rate_pct,
          ROUND(SAFE_DIVIDE(SUM(bounced), SUM(users_exposed)) * 100, 2) AS bounce_rate_pct
        FROM `{project}.{ds}.signup_prompt_experiment_mart`
        GROUP BY date, variant
        ORDER BY date ASC, variant ASC
    """)
    return {"summary": summary, "daily": daily}


# 이상 감지는 카운트 지표만 — min_volume 게이트가 "표본이 충분한가"를 카운트로
# 판단하므로, 비율 지표(engagement_rate 0~1)엔 게이트가 안 맞아 제외한다.
# 참여율 변화는 급락 알람보다 주간 브리핑에서 해석하는 게 적절.
ANOMALY_METRICS = [
    ("users", "방문자"),
    ("sessions", "세션"),
    ("page_views", "페이지뷰"),
]


def _detect_anomalies(rows: list[dict], drop_pct: float, min_volume: float) -> list[dict]:
    """dashboard_kpi 최근 행들(날짜 내림차순, 최신이 rows[0])에서 이상 급락 탐지.
    최신일 값을 '직전 7일 평균'과 비교 — 전일 단독 비교는 소규모 데이터에서
    노이즈라 평균으로 완충한다. min_volume 게이트: 기준선(평균)이 이 값 미만이면
    표본이 너무 작아 이상이라 부를 수 없으므로 건너뛴다(cry wolf 방지)."""
    if len(rows) < 2:
        return []
    latest, baseline_rows = rows[0], rows[1:8]
    anomalies = []
    for col, label in ANOMALY_METRICS:
        base_vals = [r[col] for r in baseline_rows if r.get(col) is not None]
        if not base_vals:
            continue
        avg = sum(base_vals) / len(base_vals)
        cur = latest.get(col) or 0
        if avg < min_volume:      # 기준선이 너무 작음 → 이상 판정 보류
            continue
        if cur < avg * (1 - drop_pct):
            anomalies.append({
                "metric": label, "column": col,
                "latest": round(cur, 2), "baseline_avg": round(avg, 2),
                "drop_pct": round((1 - cur / avg) * 100, 1) if avg else None,
            })
    return anomalies


def _notify(subject: str, text: str) -> dict:
    """이상 감지/계측 공백 알림을 슬랙과 이메일 양쪽으로 전송(각각 미설정 시 스킵).
    분석 완료 알림(hooks._hook_slack/_hook_email)과 같은 원칙 — 실패해도 예외 없음."""
    import urllib.request
    import json as _json
    slack_ok = False
    url = os.environ.get("SLACK_WEBHOOK_URL")
    if url:
        try:
            req = urllib.request.Request(
                url, data=_json.dumps({"text": text}).encode(),
                headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=10)
            slack_ok = True
        except Exception:
            logger.warning("slack alert 실패", exc_info=True)
    email_ok = send_email(subject, text)  # 이상 알림은 PDF 없이 본문만
    return {"slack": slack_ok, "email": email_ok}


@app.get("/anomaly-check")
def anomaly_check(drop_pct: float = 0.5, min_volume: float = 10.0):
    """최신일 지표가 직전 7일 평균 대비 drop_pct 이상 급락했는지 점검하고,
    이상이 있으면 Slack에 알린다(정기 브리핑과 별개인 '긴급 알림'). LLM 없이
    SQL+임계값이라 가볍다. 일 단위 cron으로 호출하는 용도.
    ⚠️ 현재 트래픽(일 1~5명)에선 min_volume 게이트에 막혀 거의 안 울리는 게 정상 —
    데이터가 충분히 쌓이기 전엔 이상을 함부로 선언하지 않도록 한 의도된 동작."""
    project = os.environ.get("GCP_PROJECT_ID", "")
    rows = _query(f"""
        SELECT date, users, sessions, page_views, engagement_rate
        FROM `{project}.{DATASET}.dashboard_kpi` ORDER BY date DESC LIMIT 8
    """)
    anomalies = _detect_anomalies(rows, drop_pct, min_volume)
    alerted = {}
    if anomalies:
        lines = [f":rotating_light: *지표 급락 감지* (직전 7일 평균 대비 {int(drop_pct*100)}%↓)"]
        for a in anomalies:
            lines.append(f"- {a['metric']}: {a['baseline_avg']} → {a['latest']} ({a['drop_pct']}%↓)")
        alerted = _notify("[The Formula] 지표 급락 감지", "\n".join(lines))
    return {"checked": len(rows), "anomalies": anomalies, "alerted": alerted}


# 배포된 기능이 GA4에 실제로 쏘아야 하는 커스텀 이벤트 레지스트리.
# 기능을 새로 배포하면 여기 등록 → 계측 공백(배포됐는데 이벤트 미수집)을 감시.
GA4_DATASET = "analytics_543337410"
EXPECTED_CUSTOM_EVENTS = [
    {"event": "recommendation_shown", "feature": "해시태그 관련 글 추천 — 노출"},
    {"event": "recommendation_click", "feature": "해시태그 관련 글 추천 — 클릭"},
]


def _check_instrumentation(seen: dict, days: int) -> list[dict]:
    """레지스트리의 각 기대 이벤트가 최근 GA4 데이터에 나타났는지 판정.
    seen = {event_name: (count, last_date)}. 없으면 MISSING(계측 공백)."""
    out = []
    for spec in EXPECTED_CUSTOM_EVENTS:
        ev = spec["event"]
        if ev in seen and seen[ev][0] > 0:
            out.append({**spec, "status": "OK", "count": seen[ev][0], "last_seen": seen[ev][1]})
        else:
            out.append({**spec, "status": "MISSING",
                        "note": f"기능 배포됐으나 최근 {days}일간 이벤트 미수집 — 트래킹 코드/배포 확인 필요"})
    return out


@app.get("/instrumentation-check")
def instrumentation_check(days: int = 14):
    """배포된 기능의 커스텀 이벤트가 실제로 GA4에 쌓이는지 감시하고, 누락(MISSING)이
    있으면 Slack 알림. 기능 배포와 데이터 수집 사이의 공백을 잡는다(Analytics
    Engineer의 "계측 감사관" 역할을 정기 점검으로 자동화). LLM 없이 SQL만."""
    project = os.environ.get("GCP_PROJECT_ID", "")
    names = ", ".join(f"'{s['event']}'" for s in EXPECTED_CUSTOM_EVENTS)
    rows = _query(f"""
        SELECT event_name, COUNT(*) AS n, MAX(event_date) AS last_seen
        FROM `{project}.{GA4_DATASET}.events_*`
        WHERE event_name IN ({names})
          AND _TABLE_SUFFIX >= FORMAT_DATE('%Y%m%d', DATE_SUB(CURRENT_DATE(), INTERVAL {int(days)} DAY))
        GROUP BY event_name
    """)
    seen = {r["event_name"]: (r["n"], r["last_seen"]) for r in rows}
    report = _check_instrumentation(seen, days)
    missing = [r for r in report if r["status"] == "MISSING"]
    alerted = {}
    if missing:
        lines = [":warning: *계측 공백 감지* — 배포됐으나 이벤트가 안 잡히는 기능:"]
        lines += [f"- {m['feature']} (`{m['event']}`)" for m in missing]
        alerted = _notify("[The Formula] 계측 공백 감지", "\n".join(lines))
    return {"days": days, "report": report, "missing": len(missing), "alerted": alerted}


@app.get("/insights")
def get_insights(days: int = 30):
    """run_log(실행 관측 로그) 집계 — 시스템 자기 관측 대시보드용.
    "어떤 질문이 자주 오나 / 어느 게이트에서 자주 막히나 / 환각 위험도 추이"를
    LLM 없이 SQL로 집계해 반환한다. run_log가 아직 비어있으면 빈 배열들을 준다."""
    project = os.environ.get("GCP_PROJECT_ID", "")
    ref = f"`{project}.{DATASET}.run_log`"
    where = f"WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {int(days)} DAY)"
    try:
        # 결과 유형(outcome) 분포 — 어느 게이트에서 자주 막히나
        by_outcome = _query(f"""
            SELECT outcome, COUNT(*) AS n
            FROM {ref} {where} GROUP BY outcome ORDER BY n DESC
        """)
        # 경로 분포 + 평균 지연
        by_route = _query(f"""
            SELECT route, COUNT(*) AS n, ROUND(AVG(latency_ms)) AS avg_latency_ms
            FROM {ref} {where} GROUP BY route ORDER BY n DESC
        """)
        # 환각 위험도 추이 (SUCCESS 건만, 일자별 평균)
        risk_trend = _query(f"""
            SELECT CAST(DATE(ts) AS STRING) AS date,
                   ROUND(AVG(hallucination_risk), 1) AS avg_risk,
                   ROUND(AVG(confidence), 1) AS avg_confidence,
                   COUNT(*) AS n
            FROM {ref} {where} AND outcome = 'SUCCESS'
            GROUP BY date ORDER BY date
        """)
        # 자주 오는 질문 (상위 10)
        top_questions = _query(f"""
            SELECT question, COUNT(*) AS n
            FROM {ref} {where} GROUP BY question ORDER BY n DESC LIMIT 10
        """)
        return {"window_days": days, "by_outcome": by_outcome,
                "by_route": by_route, "risk_trend": risk_trend,
                "top_questions": top_questions}
    except Exception as e:
        # run_log 테이블이 아직 없거나 조회 실패 — 빈 결과로 안전하게 응답
        logger.warning("insights 조회 실패: %s", e)
        return {"window_days": days, "by_outcome": [], "by_route": [],
                "risk_trend": [], "top_questions": []}


@app.get("/health")
def health():
    return {"status": "ok"}
