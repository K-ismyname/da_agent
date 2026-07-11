# Stop Hooks — 분석 완료(Event) 시 자동 실행되는 후속 액션(Action)
# workflows.yaml hooks.Stop 정의를 구현: report(.md) → pdf → slack
#
# [역할]
# main.py의 /analyze가 파이프라인 성공 응답을 반환한 "뒤에" 백그라운드로
# 실행되는 후처리 체인. 분석 결과(result dict)를 사람이 보기 좋은 형태(md/pdf)로
# 남기고, 팀 채널(Slack)에 알린다.
#
# [왜 이렇게 설계했나]
# - main.py의 응답 흐름과 완전히 분리한 이유: PDF 변환·Slack 전송은 실패해도
#   사용자가 받는 분석 결과 자체에는 영향이 없어야 한다. 그래서 각 훅 함수가
#   전부 실패를 예외로 던지지 않고 None/False로 삼켜서, 하나가 깨져도
#   나머지 훅은 계속 진행된다(아래 run_stop_hooks가 순차 호출하는 구조).
import os
import json
import glob
import urllib.request
from datetime import datetime

DOWNLOADS_DIR = os.path.join(os.path.dirname(__file__), "..", "downloads")


def _build_markdown(result: dict) -> str:
    """파이프라인 result dict를 사람이 읽는 마크다운 리포트로 변환.
    [왜] head_of_data(요약)뿐 아니라 data_scientist(A/B 상세)와 evaluation
    (신뢰도 점수)까지 함께 넣어, 결과 JSON을 몰라도 리포트 한 장으로 분석
    근거까지 파악할 수 있게 한다."""
    brief = result.get("head_of_data", {})
    ev = result.get("evaluation", {})
    ds = result.get("data_scientist", {})
    lines = [
        f"# Executive Report",
        f"> Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} · QA: {result.get('qa_reviewer', {}).get('verdict', '-')} · Eval: {ev.get('verdict', '-')}",
        "",
        f"## {brief.get('headline', '')}",
        "",
        "## Insights",
    ]
    for ins in brief.get("insights", []):
        lines.append(f"- **{ins.get('num', '')}** {ins.get('text', '')}")
    lines += ["", "## Actions"]
    for a in brief.get("actions", []):
        lines.append(f"- {a}")
    if ds.get("analysis_type") == "ab_test":  # A/B 분석일 때만 전용 섹션(변형 비교 표) 추가 — 일반 분석 결과엔 이 필드 자체가 없음
        lines += ["", "## A/B Test Result",
                  f"- Recommended variant: **{ds.get('recommended_variant', '-')}**",
                  f"- p-value: {ds.get('significance', {}).get('p_value', '-')}",
                  f"- Biggest funnel gap: {ds.get('biggest_gap_step', '-')}"]
        lines.append("\n| Metric | A | B | Lift % |\n|---|---|---|---|")
        for m in ds.get("primary_metrics", []):
            lines.append(f"| {m.get('metric')} (primary) | {m.get('a')} | {m.get('b')} | {m.get('lift_pct')} |")
        for m in ds.get("guardrail_metrics", []):
            lines.append(f"| {m.get('metric')} (guardrail) | {m.get('a')} | {m.get('b')} | {m.get('verdict')} |")
    lines += ["", "## Evaluation Scores",
              f"- Confidence: {ev.get('confidence', '-')}%",
              f"- Hallucination Risk: {ev.get('hallucination_risk', '-')}%",
              f"- Grounded.Numeric: {ev.get('grounded_numeric', '-')}% · Grounded.LLM: {ev.get('grounded_llm', '-')}%"]
    return "\n".join(lines)


def _hook_report(result: dict) -> str:
    """1번째 훅: 마크다운 리포트를 downloads/executive_report.md로 저장.
    같은 파일명을 매번 덮어쓰므로 "최신 분석 결과 1개"만 유지된다(이력 보관 아님)."""
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)
    path = os.path.join(DOWNLOADS_DIR, "executive_report.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(_build_markdown(result))
    return path


def _find_korean_font() -> str | None:
    """fpdf2로 실제 로드 가능한 한글 폰트를 찾는다 (존재 여부만으론 부족 — AppleGothic은 OS/2 테이블 문제로 실패).
    [왜 이렇게 짰나] CLAUDE.md에 "PDF 변환(fpdf2, 한글 폰트 자동탐색)"이라고
    명시된 요구사항. 서버 환경(macOS 로컬 vs Linux 배포)마다 설치된 폰트가
    다르므로, 하드코딩된 경로 하나 대신 여러 후보를 순서대로 실제 로드
    시도해보고(add_font) 성공하는 첫 폰트를 채택한다 — "존재"와 "로드 가능"이
    다르다는 게 핵심(주석에 명시된 AppleGothic 실패 사례)."""
    from fpdf import FPDF

    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",        # macOS (한글 포함, fpdf2 호환)
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",             # Linux
        os.path.expanduser("~/Library/Fonts/NanumGothic.ttf"),
    ]
    candidates += glob.glob("/usr/share/fonts/**/*Gothic*.ttf", recursive=True)
    for c in candidates:
        if not os.path.exists(c):
            continue
        try:
            FPDF().add_font("probe", "", c)
            return c
        except Exception:
            continue
    return None


def _hook_pdf(md_path: str) -> str | None:
    """2번째 훅: fpdf2로 마크다운 리포트를 PDF 변환 (한글 폰트 필요). 실패해도 파이프라인은 계속.
    [왜 try/except로 전체를 감쌌나] 한글 폰트를 못 찾거나 fpdf2 렌더링이
    실패해도, 이미 확보된 마크다운 리포트(_hook_report)와 Slack 알림은
    영향받지 않아야 한다 — 훅 하나의 실패가 나머지 훅을 막지 않는다는
    설계 원칙이 여기서도 반복됨."""
    try:
        from fpdf import FPDF
        font = _find_korean_font()
        if not font:
            print("[hook:pdf] Korean font not found — skipped")
            return None
        pdf = FPDF()
        pdf.add_page()
        pdf.add_font("kr", "", font)
        pdf.set_font("kr", size=10)
        with open(md_path, encoding="utf-8") as f:
            for line in f.read().splitlines():
                size = 16 if line.startswith("# ") else 13 if line.startswith("## ") else 10
                pdf.set_font("kr", size=size)
                # new_x/new_y 미지정 시 커서가 오른쪽 끝에 남아 다음 줄 폭이 0이 됨
                pdf.multi_cell(0, 6, line.lstrip("#> ").replace("**", "") or " ",
                               new_x="LMARGIN", new_y="NEXT")
        out = md_path.replace(".md", ".pdf")
        pdf.output(out)
        return out
    except Exception as e:
        print(f"[hook:pdf] skipped: {e}")
        return None


def _hook_slack(result: dict) -> bool:
    """3번째 훅: SLACK_WEBHOOK_URL 환경변수가 설정된 경우에만 실행.
    [왜 requests가 아닌 urllib을 쓰나] 이 프로젝트는 Slack 연동이 이
    한 곳뿐이라 별도 패키지(requests) 의존성을 추가하기보다 표준 라이브러리
    (urllib.request)로 충분하다고 판단한 것으로 보인다."""
    url = os.environ.get("SLACK_WEBHOOK_URL")
    if not url:
        return False  # 웹훅 미설정 시 조용히 스킵 — CLAUDE.md "Slack 알림(설정 시)"과 일치, 필수 기능이 아님
    brief = result.get("head_of_data", {})
    ev = result.get("evaluation", {})
    payload = {"text": (
        f":bar_chart: *분석 완료* — {brief.get('headline', '')}\n"
        f"QA: {result.get('qa_reviewer', {}).get('verdict', '-')} · "
        f"Confidence: {ev.get('confidence', '-')}% · "
        f"Hallucination Risk: {ev.get('hallucination_risk', '-')}%"
    )}
    try:
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        print(f"[hook:slack] failed: {e}")
        return False


def run_stop_hooks(result: dict) -> dict:
    """Event(분석 완료) → Hook 체인 실행: report.md → report.pdf → slack.
    [역할] main.py의 background.add_task(run_stop_hooks, result)로 호출되는
    진입점. 3개 훅을 순서대로(md 없이는 pdf를 만들 수 없으므로 순차) 실행하고,
    각 단계의 결과 경로/성공여부를 status dict로 모아 반환한다(다만 이 반환값은
    background task라 실제로 아무도 읽지 않음 — 로깅/디버깅 목적에 가깝다)."""
    status: dict = {}
    md_path = _hook_report(result)
    status["report"] = md_path
    pdf_path = _hook_pdf(md_path)
    status["pdf"] = pdf_path
    status["slack"] = _hook_slack(result)
    return status
