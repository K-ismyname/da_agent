# 각 에이전트 노드 함수 — LangGraph StateGraph에 연결
#
# [역할]
# 파이프라인(Supervisor → Product Analyst → ... → Head of Data)을 실제로 실행하는
# 노드 함수들. 각 함수는 AnalysisState를 받아 자기 결과만 담은 dict를 반환하고,
# LangGraph(graph.py)가 이를 State에 병합한다. tools/bigquery.py가 "판단 없는
# 실행 계층"이라면, 이 파일은 "LLM이 실제로 판단을 내리는 에이전트 계층"이다.
# Supervisor의 route(nonanalytic/simple/complex)에 따라 실제로 도는 노드가 달라진다.
#
# [왜 이렇게 설계했나]
# - 노드 함수가 전부 같은 시그니처(state -> dict)인 이유: LangGraph 노드 규약을
#   맞춰야 graph.py에서 노드 순서를 자유롭게 배선할 수 있기 때문.
# - 한 파일에 모은 이유: llm, KPI_DICTIONARY, SKILLS 같은 전역 리소스를
#   공유해야 해서 — 노드마다 파일을 쪼개면 이 로딩을 중복하거나 별도 모듈로
#   다시 옮겨야 해서 오히려 복잡해진다.
# - LLM 호출 실패 방어: _invoke_json/_invoke_with_tools가 예외 대신 {"error":...}
#   dict를 반환하므로, 노드 하나의 일시적 실패로 파이프라인 전체가 죽지 않는다.
import glob
import json
import os
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from agent_backend.state import AnalysisState
from agent_backend.tools.bigquery import (
    query_mart, get_date_range, get_experiment_summary,
    run_significance_test, EXPERIMENT_METRICS,
)

# Data Scientist가 A/B 질문에 맞춰 고를 수 있는 "실제" 등록 실험 목록 텍스트.
# EXPERIMENT_METRICS(tools/bigquery.py)가 SSOT — 여기서 설명만 프롬프트용으로
# 뽑아 쓴다. 새 실험을 등록해도 이 문자열은 자동으로 갱신된다(하드코딩 없음).
_REAL_EXPERIMENTS_TEXT = "\n".join(
    f'- "{name}": {cfg["description"]}'
    for name, cfg in EXPERIMENT_METRICS.items() if cfg.get("real")
)

llm = ChatOpenAI(model="gpt-4o", temperature=0)  # temperature=0: 같은 입력엔 최대한 같은 출력 — 창의성보다 재현성이 중요한 분석 도메인

# ── SSOT 문서 로드 (knowledge/ + skills/) ─────────────────────────────
# 왜 파일을 읽어서 프롬프트에 주입하나: CLAUDE.md의 "KPI SSOT / No hardcoding"
# 원칙 실행부. KPI 정의를 코드에 하드코딩하면 knowledge/kpi_dictionary.md가
# 바뀔 때마다 코드도 고쳐야 한다. 대신 파일을 그대로 읽어 프롬프트에 넣으면
# 문서만 수정해도 모든 에이전트가 동일한 최신 정의를 참조하게 된다.
_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


KPI_DICTIONARY = _read(os.path.join(_ROOT, "knowledge", "kpi_dictionary.md"))
BUSINESS_CONTEXT = _read(os.path.join(_ROOT, "knowledge", "business_context.md"))
AB_TEST_FRAMEWORK = _read(os.path.join(_ROOT, "knowledge", "ab_test_framework.md"))

# skills/<category>/<name>.md → {name: content}
SKILLS = {
    os.path.splitext(os.path.basename(p))[0]: _read(p)
    for p in glob.glob(os.path.join(_ROOT, "skills", "*", "*.md"))
}


def _skill_context(names: list[str]) -> str:
    """스킬 문서 여러 개를 프롬프트용 텍스트로 병합."""
    docs = [SKILLS[n] for n in names if n in SKILLS]
    return "\n\n---\n\n".join(docs) if docs else ""


# Data Scientist 일반 분기에 항상 주입하는 분석 방법론 문서 = skills/analytics/
# 카테고리(ab_test_analysis는 A/B 전용 분기가 따로 하드코딩으로 로드하므로 제외).
# 예전엔 Planner가 LLM으로 골랐으나, 유효 선택지가 이 4개뿐이고 문서도 짧아
# (합쳐 ~1.5k토큰) 그냥 다 주입한다 — Planner LLM 호출 하나를 없애고, Planner가
# 엉뚱한 카테고리 스킬을 고르던 버그도 제거.
GENERAL_ANALYSIS_SKILLS = [
    "funnel_analysis", "cohort_analysis",
    "journey_analysis", "marketing_channel_analysis",
]


def _extract_json(content: str) -> dict:
    """LLM 응답에서 JSON 추출. 마크다운 블록·trailing text 모두 처리."""
    # 왜 필요한가: 프롬프트에 "Respond ONLY with valid JSON"이라고 못박아도
    # LLM은 종종 ```json ... ``` 코드블록으로 감싸거나 앞뒤에 설명 문장을
    # 붙인다. json.loads()는 그런 여분 텍스트가 있으면 바로 실패하므로,
    # 파싱 전에 방어적으로 순수 JSON 부분만 잘라낸다.
    # ```json ... ``` 또는 ``` ... ``` 블록 우선
    for marker in ("```json", "```"):
        if marker in content:
            inner = content.split(marker)[1]
            content = inner.split("```")[0]
            break
    content = content.strip()
    # 중괄호 시작 위치 찾기 (앞뒤 설명 텍스트 제거) — 코드블록이 없어도
    # "여기 결과입니다: {...}" 같은 서두 문장을 잘라내기 위한 2차 방어
    start = content.find("{")
    end = content.rfind("}") + 1
    if start != -1 and end > start:
        content = content[start:end]
    return json.loads(content)  # 그래도 실패하면 예외가 그대로 올라감 — 상위에서 잡지 않음(의도적으로 크래시해 문제를 바로 드러냄)


def _safe_dict(result, where: str) -> dict:
    """LLM 결과가 dict가 아니면(파싱 결과가 리스트/스칼라 등) 안전한 error dict로 강제.
    왜: 각 노드는 반환값이 dict라고 가정하고 .get()/json.dumps로 소비한다. dict가
    아니면 downstream이 크래시하므로 여기서 타입을 보장한다(gate 노드는 verdict가
    없으니 FAIL로 안전하게 떨어지고, 나머지는 빈 분석으로 이어진다)."""
    if isinstance(result, dict):
        return result
    return {"error": f"{where}: dict 아닌 출력({type(result).__name__})"}


def _invoke_json(system: str, user: str) -> dict:
    """툴 없이 JSON 응답을 바로 반환하는 단순 LLM 호출.
    LLM 호출/파싱 실패 시 예외를 던지는 대신 {"error": ...} dict를 반환한다 —
    노드 하나의 일시적 실패(rate limit 등)로 파이프라인 전체가 죽지 않도록."""
    try:
        res = llm.invoke([SystemMessage(system), HumanMessage(user)])
        return _safe_dict(_extract_json(res.content), "LLM JSON 파싱")
    except Exception as e:
        return {"error": f"LLM 호출 실패: {e}"}


MAX_TOOL_ROUNDS = 10  # 무한 툴 호출 루프 방지 — LLM 호출 비용 상한


def _invoke_with_tools(system: str, user: str, tools) -> dict:
    """Tool calling 루프 — finish_reason=stop 또는 라운드 상한까지 반복.

    [역할] 이 프로젝트에서 "에이전트가 자율적으로 도구를 쓴다"는 게 실제로
    무엇을 의미하는지 보여주는 핵심 함수. LLM이 스스로 "도구를 몇 번, 어떤
    순서로 부를지" 결정하게 하고, 이 함수는 그 요청을 실행해주는 오케스트레이터
    역할만 한다 — 즉 이 함수 자체는 판단하지 않고, LLM의 판단을 반복 실행할
    뿐이다.

    [왜 이렇게 설계했나]
    - 라운드 상한(MAX_TOOL_ROUNDS)이 있는 이유: LLM이 도구 호출을 끝없이
      반복하면(예: 같은 쿼리를 계속 재호출) 비용이 무한정 늘어난다. 상한을
      걸어 최악의 경우에도 비용을 예측 가능하게 만든다.
    - 마지막 라운드에 도구를 떼는 이유(78행): 상한에 도달했는데도 LLM이 또
      도구를 부르려 하면 JSON 응답을 영영 못 받는다. 강제로 텍스트 응답만
      받게 해서 파이프라인이 반드시 끝나도록 보장한다.
    - 툴 실행 실패를 예외로 던지지 않고 문자열로 돌려주는 이유(85~89행):
      BigQuery 순간 장애 등으로 도구 호출이 실패해도 파이프라인 전체가
      죽지 않게 하기 위함. LLM이 "TOOL ERROR: ..." 메시지를 읽고 재시도하거나
      다른 방식으로 우회할 기회를 준다.
    """
    from langchain_core.messages import ToolMessage

    messages = [SystemMessage(system), HumanMessage(user)]
    bound = llm.bind_tools(tools)  # LLM에 "이런 도구들을 쓸 수 있다"는 스키마를 알려줌
    tool_map = {t.name: t for t in tools}  # LLM이 응답에서 준 도구 이름 문자열 → 실제 실행 가능한 함수로 매핑

    # LLM 호출(rate limit 등)이나 최종 JSON 파싱이 실패해도 예외를 던지는 대신
    # {"error": ...}로 안전하게 반환 — _invoke_json과 동일한 실패 방어 원칙.
    # (개별 툴 실행 실패는 아래 안쪽 try에서 이미 문자열로 흡수한다.)
    try:
        for round_no in range(MAX_TOOL_ROUNDS):
            # 마지막 라운드에는 툴을 떼고 강제로 답변만 받는다
            res = (llm if round_no == MAX_TOOL_ROUNDS - 1 else bound).invoke(messages)
            messages.append(res)  # 대화 히스토리에 LLM 응답을 계속 누적 — 다음 라운드에서 이전 맥락을 유지하기 위함

            if not res.tool_calls:
                # LLM이 더 이상 도구가 필요 없다고 판단 → 최종 답변으로 간주하고 루프 종료
                return _safe_dict(_extract_json(res.content), "LLM JSON 파싱")

            for tc in res.tool_calls:
                # 툴 실패는 파이프라인 크래시 대신 에러 문자열로 — 에이전트가 읽고 재시도
                try:
                    result = tool_map[tc["name"]].invoke(tc["args"])
                except Exception as e:
                    result = f"TOOL ERROR: {e}"
                # ToolMessage로 결과를 대화에 추가 — LLM은 다음 턴에 이 메시지를 보고 해석/재판단한다
                messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))
    except Exception as e:
        return {"error": f"tool-calling LLM 호출 실패: {e}"}

    # 상한 초과는 설계상 거의 발생 안 함(마지막 라운드에서 강제 종료되므로)
    return {"error": f"tool loop exceeded {MAX_TOOL_ROUNDS} rounds"}


# ── 0. Supervisor (라우팅 게이트) ─────────────────────────────────────
# [역할] 파이프라인 맨 앞에서 질문 유형을 판단해 "얼마나 무거운 경로로 보낼지"를
# 결정한다. 모든 질문에 전체 에이전트를 다 돌리면 인사말 같은 것에도 억지 분석이
# 나오고 비용도 낭비되므로, 여기서 3갈래로 나눈다.
# [왜] Planner는 "어떤 스킬이 필요한지"만 추천할 뿐 실행 경로를 못 바꿨다(graph.py
# 고정 배선). Supervisor는 graph.py의 조건부 엣지와 짝을 이뤄 실제로 경로 자체를
# 분기시킨다 — "분석 대상이 아닌 질문은 에이전트를 아예 안 돌린다"를 코드로 강제.
# [실패 방어] 이 노드는 모든 요청이 거치는 첫 관문(SPOF)이지만, _invoke_json이
# 실패 시 {"error":...} dict를 반환하므로 여기서 예외가 터지지 않는다. route 키가
# 없으면 graph._route()가 complex로 안전하게 처리한다(애매하면 무거운 쪽 원칙).
def node_supervisor(state: AnalysisState) -> dict:
    result = _invoke_json(
        """You are the Supervisor of an AI data team for a community website (GA4 data).
Classify the user's question into exactly one route:
- "nonanalytic": greeting, small talk, or a question about what this system can do
  (not a request to analyze the website's data). NO agents should run.
- "simple": a direct single-number/single-fact lookup answerable from ONE mart
  WITHOUT ambiguity about which mart. If the metric name could plausibly live in
  more than one mart (e.g. "이탈률" could mean funnel drop-off OR an experiment's
  bounce rate), that is NOT simple — pick complex so Product Analyst can disambiguate
  the mart first. Reserve simple for unambiguous single-fact lookups
  (e.g. "지난주 방문자 수는?", "가장 인기 페이지는?").
- "complex": needs reasoning across multiple marts, root-cause analysis, an
  A/B test analysis, or any metric name that maps to more than one mart
  (e.g. "왜 이탈률이 높아?", "이탈률 얼마야?", "가입 전환 개선점은?", "A/B 결과 분석해줘").
When unsure between simple and complex, choose complex. Respond ONLY with valid JSON.""",
        f"""Question: "{state['question']}"

Return:
{{
  "route": "nonanalytic|simple|complex",
  "reason": "한 줄 이유",
  "message": "route가 nonanalytic일 때만: 사용자에게 보여줄 한국어 안내 (이 시스템이 커뮤니티 GA4 데이터 분석을 해준다는 안내). 그 외에는 빈 문자열"
}}"""
    )
    return {"supervisor": result}


# [Planner 노드 제거, 2026-07-10] Planner의 유일한 산출물(skills)은 Data
# Scientist 일반 분기에만 주입됐는데, 유효 선택지가 skills/analytics/ 5개뿐이고
# A/B 스킬은 DS가 키워드로 자체 판별하므로, LLM으로 고를 실익이 없었다(오히려
# 다른 카테고리 스킬을 잘못 고르는 버그가 있었음). 스킬은 이제 DS 일반 분기가
# GENERAL_ANALYSIS_SKILLS를 직접 주입한다. complex 경로는 Product Analyst부터 시작.


# ── 1. Product Analyst ────────────────────────────────────────────────
# [역할] 도구 없이(순수 LLM 판단만으로) business_context.md를 근거 삼아 분석
# 방향과 가설을 세운다. 아직 실제 데이터를 조회하기 전 단계 — "무엇을 볼지"를
# 정하는 기획 단계에 해당한다.
def node_product_analyst(state: AnalysisState) -> dict:
    result = _invoke_json(
        f"""You are a Product Analyst for a community website.
Use the business context below as SSOT — do not assume anything beyond it.

<business_context>
{BUSINESS_CONTEXT}
</business_context>

The values shown below are INSTRUCTIONS in angle brackets — replace every <...>
with your own content specific to this question. NEVER return the placeholder
text itself. Respond ONLY with valid JSON.""",
        f"""Question: "{state['question']}"

Return:
{{
  "headline": "<이 질문에 대한 분석 방향을 한 문장으로 요약>",
  "focus_metrics": ["<이 질문에서 봐야 할 핵심 지표 1~3개>"],
  "hypothesis": "<데이터를 보기 전 세운 가설>",
  "analysis_direction": "<어떤 마트를 어떤 순서로 볼지 구체적 방향>",
  "activity": "product_analyst: 방향 설정 완료"
}}"""
    )
    return {"product_analyst": result}


# ── 2. Analytics Engineer (BigQuery 툴 사용) ──────────────────────────
# [역할] 본격 분석 전에 데이터 신뢰도를 먼저 점검하는 게이트키퍼. query_mart로
# 실제 값을 훑어보고 결측치/이상치/날짜 커버리지를 판단해 trust_level을 매긴다.
# [왜] Data Scientist가 저품질 데이터로 바로 분석에 들어가면 잘못된 결론이
# 나올 수 있어, 분석 전 단계에서 한 번 걸러내는 검증 계층을 따로 뒀다.
def node_analytics_engineer(state: AnalysisState) -> dict:
    result = _invoke_with_tools(
        """You are an Analytics Engineer — the data-quality gatekeeper before analysis.
Use the tools to query the marts this question needs and judge whether the data is
trustworthy enough to analyze. Check missing values, anomalies, AND sample size /
date coverage.

trust_level rules (be strict — you are a gate, not a rubber stamp):
- "LOW": the data can't support a reliable answer — e.g. the needed mart is empty,
  or a metric flagged LOW-trust in the KPI Dictionary is central to the question
  (channel data is all Direct because UTM is unset). A LOW verdict STOPS the
  pipeline, so use it when analyzing anyway would mislead.
- "MEDIUM": data is usable but limited — notably a SMALL SAMPLE (e.g. only a few
  days of data, single-digit users per group). Do NOT rate small-sample data HIGH.
- "HIGH": ample, clean, well-covered data with no material caveats.
For EACH concrete problem, also state what would fix it (a data/instrumentation
action, not a re-analysis) — e.g. "UTM 파라미터를 유입 링크에 설정해야 채널 분석
가능", "실험 기능 배포 후 며칠 트래픽이 쌓여야 표본 충분". After querying,
respond ONLY with valid JSON.""",
        f"""Question: "{state['question']}"
Product Analyst direction: {json.dumps(state['product_analyst'], ensure_ascii=False)}

Use query_mart and get_date_range tools as needed, then return:
{{
  "trust_level": "HIGH|MEDIUM|LOW",
  "tables_queried": ["테이블명"],
  "issues": [{{"problem": "구체적 문제 (표본 크기·결측·이상치 등)", "fix": "이를 해결할 데이터/계측 조치"}}],
  "confidence": 0-100,
  "activity": "analytics_engineer: 데이터 검증 완료"
}}""",
        [query_mart, get_date_range]
    )
    return {"analytics_engineer": result}


# ── 3. Data Scientist (BigQuery 툴 사용) ──────────────────────────────
# [역할] 파이프라인의 핵심 분석 노드. 실제 인사이트(root_cause, funnel_insight
# 등)를 만들어낸다. 두 프롬프트 세트(A/B 전용 vs 일반)를 분기해서 쓴다.
# [왜 분기했나] A/B 테스트는 Primary/Guardrail/Funnel이라는 전용 통계 프레임과
# z-test 도구가 필요해 일반 분석과 프롬프트·툴셋이 완전히 다르다. 하나의
# 범용 프롬프트로 억지로 합치면 A/B 규칙(p-value는 반드시 도구로 계산 등)이
# 희석될 위험이 있어 분리했다.
def node_data_scientist(state: AnalysisState) -> dict:
    # A/B 판별은 질문 키워드로 직접 한다(예전엔 Planner가 고른 skills도 참고했으나
    # Planner 제거됨). 이 판별이 A/B 전용 분기 진입 여부를 결정한다.
    is_ab_test = any(
        k in state["question"].lower() for k in ["a/b", "ab test", "variant", "실험", "테스트"]
    )

    if is_ab_test:
        result = _invoke_with_tools(
            f"""You are a Data Scientist running an A/B test analysis (skill: ab_test_analysis).
Follow the AB test framework, skill document, and KPI Dictionary (SSOT) below —
never redefine a metric or invent a different significance/decision rule.

<ab_test_framework>
{AB_TEST_FRAMEWORK}
</ab_test_framework>

<kpi_dictionary>
{KPI_DICTIONARY}
</kpi_dictionary>

<skill>
{SKILLS.get("ab_test_analysis", "")}
</skill>

Registered REAL experiments — this is a CLOSED list, not examples:
{_REAL_EXPERIMENTS_TEXT}

STOP-AND-CHECK before calling any tool: does the question's TOPIC match one of
these experiments' descriptions above (same subject — banner vs sort vs whatever
else)? A question about a topic not in this list (e.g. churn/탈퇴율, pricing,
notifications — anything not literally described above) has NO match. In that
case you MUST set "experiment_match": false, "experiment": null, call NO tools,
and explain in root_cause that no registered experiment covers this question.
Do NOT default to the closest-sounding experiment just because it's the only one
available — an unrelated question with a confident wrong answer is worse than
admitting there's no data for it.
Rules when there IS a match: use get_experiment_summary(experiment=<picked name>)
for all metrics (never per-row averages, never ab_test_mart — that mart is an
unrelated demo dataset); use run_significance_test(experiment=<same picked name>)
for the p-value (NEVER estimate it yourself); report absolute counts alongside
rates; state the sample-size caveat if denominators are small; apply the decision
rule from <ab_test_framework> exactly (do not soften or override it). Use Korean
for insights. Respond ONLY with valid JSON.""",
            f"""Question: "{state['question']}"
Analysis direction: {json.dumps(state['product_analyst'], ensure_ascii=False)}
Data quality: {json.dumps(state['analytics_engineer'], ensure_ascii=False)}

First decide experiment_match, then (only if true) use tools, then return:
{{
  "experiment_match": true,
  "experiment": "the registered experiment name you picked, or null if no match",
  "analysis_type": "ab_test",
  "period": {{"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}},
  "primary_metrics": [{{"metric": "실제 지표명 (예: ApplyReachRate/ArticleClickRate)", "a": 0.0, "b": 0.0, "lift_pct": 0.0}}],
  "significance": {{"p_value": 0.0, "significant": true}},
  "guardrail_metrics": [{{"metric": "실제 지표명 (예: BounceRate)", "a": 0.0, "b": 0.0, "verdict": "OK|DEGRADED"}}],
  "recommended_variant": "A|B|HOLD|N/A",
  "root_cause": "핵심 원인 (한국어) — experiment_match가 false면 왜 매칭되는 실험이 없는지",
  "evidence": ["근거1", "근거2", "근거3"],
  "sample_size_caveat": "표본이 작으면 명시, 충분하면 빈 문자열",
  "next_actions": ["액션1", "액션2"],
  "activity": "data_scientist: A/B 테스트 분석 완료"
}}""",
            [get_experiment_summary, run_significance_test, query_mart, get_date_range]
        )
        return {"data_scientist": result}

    result = _invoke_with_tools(
        f"""You are a Data Scientist. Use tools to query the marts you need for analysis.
Follow the skill documents below — they define the analysis steps, QA checklist,
and anti-patterns you MUST respect. All KPI definitions come from the KPI Dictionary
(SSOT) — never redefine a metric yourself. Use Korean for insights.

<kpi_dictionary>
{KPI_DICTIONARY}
</kpi_dictionary>

<skills>
{_skill_context(GENERAL_ANALYSIS_SKILLS)}
</skills>

Only query and report on the marts RELEVANT to the question — do not fabricate a
funnel/channel/cohort insight if the question isn't about it.

CRITICAL — "answerable" is TRUE only if you actually queried the specific mart the
question directly asks about AND that mart returned real rows. It is FALSE if:
  - the required mart is missing / empty / returned no rows, OR
  - it is flagged LOW trust in the KPI Dictionary (e.g. channel = all Direct, UTM unset), OR
  - you could only "answer" by substituting a DIFFERENT mart than the one asked about.
"직접 데이터는 없지만 관련 분석으로 대신 답한다"는 answerable=FALSE 이다 —
관련 우회 분석을 곁들이는 것은 괜찮지만, 그렇다고 answerable을 true로 올리지 마라.
예: "추천 클릭률"을 물었는데 recommendation_mart가 비어있으면 → answerable=false
(퍼널로 대신 답해도 여전히 false). "채널 성과"는 UTM 미설정이라 항상 false.
When answerable=false, root_cause must state plainly that the asked-for data
isn't available. The values below are INSTRUCTIONS in angle brackets; replace each
<...> with real content and OMIT insight keys that don't apply.
Respond ONLY with valid JSON after querying.""",
        f"""Question: "{state['question']}"
Analysis direction: {json.dumps(state['product_analyst'], ensure_ascii=False)}
Data quality: {json.dumps(state['analytics_engineer'], ensure_ascii=False)}

First decide answerable, then use query_mart / get_date_range only for the marts
this question actually needs. Include an insight key ONLY if you queried that mart
for THIS question (funnel_insight / channel_insight / cohort_insight / landing_insight):
{{
  "answerable": true,
  "root_cause": "<이 질문의 핵심 답/원인, 실제 조회한 수치 포함. answerable=false면 왜 답할 수 없는지>",
  "insights": {{"<해당되는 마트명 기반 키>": "<그 마트에서 실제로 본 인사이트>"}},
  "evidence": ["<실제 조회한 수치 근거. 답할 수 없으면 빈 배열>"],
  "activity": "data_scientist: 분석 완료"
}}""",
        [query_mart, get_date_range]
    )
    return {"data_scientist": result}


# ── 4. QA Reviewer ────────────────────────────────────────────────────
# [역할] 도구 없이, 앞 세 에이전트의 출력만 놓고 "숫자와 결론이 서로 모순되지
# 않는지"를 판정한다. 예: Data Scientist가 "매출이 늘었다"고 했는데 Analytics
# Engineer가 해당 기간 데이터를 LOW 신뢰도로 판정했다면 여기서 걸러진다.
# [왜] graph.py의 _qa_gate가 여기 verdict를 보고 파이프라인 계속/중단을 결정 —
# CLAUDE.md "QA Reviewer FAIL → 결과 출력 불가" 원칙의 실행 지점.
def node_qa_reviewer(state: AnalysisState) -> dict:
    result = _invoke_json(
        """You are a QA Reviewer doing a fast logical-consistency check across agent
outputs (you do NOT re-query data — that's the Evaluator's job). Check specifically:
1) Do Data Scientist's numbers stay within the marts/period the Analytics Engineer
   actually queried? Flag numbers that reference data nobody looked at.
2) Does the confidence of the conclusion match the data quality? If Analytics
   Engineer rated trust MEDIUM/LOW or listed small-sample issues, a sweeping,
   over-confident conclusion is an inconsistency → WARN or FAIL.
3) Do the stated evidence and root_cause actually support each other, with no
   internal contradiction (e.g. "이탈률이 낮다" but evidence shows 85%)?
Verdict: FAIL for a real contradiction or unsupported claim; WARN for
over-confidence on limited data; PASS only if consistent. Put concrete problems
in "issues". Respond ONLY with valid JSON.""",
        f"""All agent outputs:
{json.dumps({
    "product_analyst": state["product_analyst"],
    "analytics_engineer": state["analytics_engineer"],
    "data_scientist": state["data_scientist"],
}, ensure_ascii=False)}

Return:
{{
  "verdict": "PASS|WARN|FAIL",
  "issues": ["구체적 불일치 (없으면 빈 배열)"],
  "confidence": 0-100,
  "activity": "qa_reviewer: 검증 완료"
}}"""
    )
    return {"qa_reviewer": result}


# ── 4.5 Evaluator (skill: evaluation_scoring) ─────────────────────────
# [역할] "판정은 LLM, 집계는 코드"로 나뉜 2단계 검증. _judge_claims가 개별
# 주장을 하나씩 PASS/FAIL 판정하면(LLM), node_evaluator가 그 판정들을 모아
# 점수로 환산한다(결정론적 파이썬 코드).
# [왜 두 단계로 나눴나] 만약 "confidence 점수를 몇 점으로 매길지"까지 LLM에게
# 맡기면, 그 점수 계산 자체도 환각(부정확한 어림짐작) 대상이 된다. 개별 사실
# 확인(YES/NO 판정)은 LLM이 잘하지만, 그 결과를 집계하는 산술은 코드가 훨씬
# 정확하고 재현 가능하므로 역할을 분리했다.
def _judge_claims(state: AnalysisState) -> dict:
    """LLM judge: check every claim in data_scientist output against mart evidence."""
    return _invoke_with_tools(
        """You are an Evaluation judge (skill: evaluation_scoring).
Re-query the marts to verify the analysis. For EVERY numeric claim in the
analysis output, compare against actual mart data (tolerance ±2%):
PASS (matches), PARTIAL (within ±2%), FAIL (mismatch or unverifiable).
For every qualitative statement, judge if evidence supports it: YES / PARTIAL / NO.
Do NOT compute aggregate scores — just list the checks. Respond ONLY with valid JSON.""",
        f"""Analysis output to verify:
{json.dumps(state['data_scientist'], ensure_ascii=False)}

Use tools to fetch evidence, then return:
{{
  "numeric_checks": [{{"claim": "...", "expected": "...", "actual": "...", "result": "PASS|PARTIAL|FAIL"}}],
  "statement_checks": [{{"statement": "...", "judgment": "YES|PARTIAL|NO", "reason": "..."}}],
  "evidence_sources": ["signup_prompt_experiment_mart", "..."]
}}""",
        [get_experiment_summary, run_significance_test, query_mart, get_date_range]
    )


def node_evaluator(state: AnalysisState) -> dict:
    """Deterministic scoring: Confidence / Hallucination Risk / Grounded / Verdict."""
    judged = _judge_claims(state)  # LLM이 개별 주장들을 판정한 원시 결과

    nc = judged.get("numeric_checks", [])   # 숫자 주장 판정 리스트 (PASS/PARTIAL/FAIL)
    sc = judged.get("statement_checks", [])  # 서술 주장 판정 리스트 (YES/PARTIAL/NO)

    # LLM 출력에 키가 빠져도 크래시하지 않도록 .get() + 기본값 FAIL 처리
    # (관찰기록 1376) — LLM이 스키마를 100% 지키지 않을 수 있다는 전제하에
    # 항상 최악(FAIL)으로 안전하게 기울이는 방어적 기본값
    def _score_numeric():
        if not nc:
            return 0.0
        # PASS=1점, PARTIAL=0.5점, FAIL=0점으로 환산 후 백분율화 — 부분 점수를 허용해
        # "완전히 틀림"과 "±2% 오차 내"를 구분한다
        pts = sum(1.0 if c.get("result") == "PASS" else 0.5 if c.get("result") == "PARTIAL" else 0.0 for c in nc)
        return round(pts / len(nc) * 100, 1)

    def _score_llm():
        if not sc:
            return 0.0
        pts = sum(1.0 if c.get("judgment") == "YES" else 0.5 if c.get("judgment") == "PARTIAL" else 0.0 for c in sc)
        return round(pts / len(sc) * 100, 1)

    grounded_numeric = _score_numeric()
    grounded_llm = _score_llm()
    # hallucination_risk = 100 - 평균 근거점수. "근거가 탄탄할수록(grounded 높을수록)
    # 환각 위험은 낮다"는 반비례 관계를 그대로 수식화.
    # 버그 수정(2026-07-09): 예전엔 (grounded_numeric + grounded_llm)/2로 항상 두
    # 차원을 평균냈는데, 한쪽 주장이 아예 없으면(예: 숫자 주장 0개) 그 차원이 0점으로
    # 잡혀 평균을 끌어내렸다 — 정성 주장이 전부 근거 있어도 risk가 50%로 나오는
    # 억울한 WARN이 생겼다. 이제 실제로 검증한 차원만 평균에 넣는다.
    present = []
    if nc:
        present.append(grounded_numeric)
    if sc:
        present.append(grounded_llm)
    avg_grounded = sum(present) / len(present) if present else 0.0
    hallucination_risk = round(100 - avg_grounded, 1)

    # 숫자 판정(PASS/PARTIAL/FAIL)과 서술 판정(YES/PARTIAL/NO)의 라벨 체계가 달라서
    # 하나의 척도(PASS/PARTIAL/FAIL)로 통일한 뒤 합쳐서 전체 confidence를 계산
    all_checks = [c.get("result", "FAIL") for c in nc] + [
        {"YES": "PASS", "PARTIAL": "PARTIAL", "NO": "FAIL"}.get(c.get("judgment"), "FAIL") for c in sc
    ]
    n_pass = all_checks.count("PASS")
    n_partial = all_checks.count("PARTIAL")
    confidence = round((n_pass + n_partial * 0.5) / len(all_checks) * 100, 1) if all_checks else 0.0

    # 임계값 기반 최종 verdict — CLAUDE.md "Evaluator FAIL 시 중단" 원칙의 실제 기준값
    if confidence >= 70 and hallucination_risk <= 30:
        verdict = "PASS"
    elif confidence >= 50 and hallucination_risk <= 50:
        verdict = "WARN"
    else:
        verdict = "FAIL"

    return {"evaluation": {
        "confidence": confidence,
        "hallucination_risk": hallucination_risk,
        "grounded_numeric": grounded_numeric,
        "grounded_llm": grounded_llm,
        "verdict": verdict,
        "checks": {"pass": n_pass, "partial": n_partial, "fail": all_checks.count("FAIL"), "total": len(all_checks)},
        "investigation_log": {
            "numeric_checks": nc,
            "statement_checks": sc,
            "evidence_sources": judged.get("evidence_sources", []),
        },
        "activity": "evaluator: 평가 완료",
    }}


# ── 5. Head of Data ───────────────────────────────────────────────────
# [역할] 파이프라인 최종 노드. 앞 노드들의 결과를 취합해 사람이 읽을 Executive
# Brief(핵심 인사이트 3개, 액션 3개)를 한국어로 작성한다.
# [왜 confidence/qa_verdict를 LLM이 안 만드나] 이 두 값은 이미 Evaluator가 코드로
# 결정론적으로 계산했고(confidence) QA Reviewer가 판정했다(verdict). LLM에게 다시
# 적게 하면 환각으로 실제와 다른 값이 나온다(실측: Eval이 92.9로 계산했는데 LLM은
# 50이라 지어냄). 그래서 LLM은 글(headline/insights/actions)만 쓰고, 검증 숫자는
# 여기서 실제 값으로 덮어쓴다 — CLAUDE.md "환각 점수는 LLM이 아니라 코드가 계산".
def node_head_of_data(state: AnalysisState) -> dict:
    result = _invoke_json(
        """You are the Head of Data. Write the final executive brief in Korean.
Max 3 insights, max 3 actions. Do NOT output confidence or verdict scores —
those are computed elsewhere. Respond ONLY with valid JSON.""",
        f"""All pipeline outputs:
{json.dumps({k: (
    {kk: vv for kk, vv in state.get(k, {}).items() if kk != "investigation_log"}
    if k == "evaluation" else state.get(k)
    # investigation_log는 개별 검증 내역(수십 개 항목)을 담고 있어 매우 길다 —
    # Head of Data 프롬프트에는 요약 점수만 필요하므로 여기서 제외해 토큰을 아낀다
) for k in [
    "product_analyst", "analytics_engineer",
    "data_scientist", "qa_reviewer", "evaluation"
]}, ensure_ascii=False)}

Return:
{{
  "headline": "가장 중요한 인사이트 한 문장",
  "insights": [{{"num": "INSIGHT 1", "text": "수치 포함"}}, ...],
  "actions": ["액션1", "액션2", "액션3"],
  "activity": "head_of_data: executive brief 완료"
}}"""
    )
    # confidence/qa_verdict는 LLM 출력이 아니라 실제 계산·판정된 값으로 덮어쓴다.
    # (LLM이 result에 이 키를 넣었더라도 무조건 신뢰 값으로 교체 — 환각 차단)
    if isinstance(result, dict):
        result["confidence"] = state.get("evaluation", {}).get("confidence", 0)
        # qa_verdict: QA Reviewer가 돌지 않은 simple 경로면 Evaluator verdict로 대체
        result["qa_verdict"] = (
            state.get("qa_reviewer", {}).get("verdict")
            or state.get("evaluation", {}).get("verdict", "N/A")
        )
    return {"head_of_data": result}
