# Skill: marketing_channel_analysis

## Goal
Describe the traffic channel mix — BUT only descriptively. This community has NOT
set UTM parameters, so nearly all traffic collapses into "Direct" and true channel
attribution is unreliable (kpi_dictionary.md marks Channel Attribution as 신뢰도 LOW).

## ⚠️ Trust gate (read before analyzing)
UTM 미설정 상태에서는 채널별 우열·우선순위 결론을 내면 안 된다. 이 스킬의 산출물은
"채널이 이렇게 나뉘어 보인다(단, 신뢰 불가)"까지이고, "어느 채널을 키워라" 같은
액션 제안은 금지다. 채널 질문은 대체로 answerable=false로 처리되어야 한다 —
먼저 UTM을 설정해 데이터를 신뢰 가능하게 만드는 것이 선행 조치다.

## Primary Owner
Data Scientist

## Input Mart
- marketing_channel_mart — columns: `date`, `channel_group`, `sessions`, `users`,
  `engagement_rate` (date 차원 있음 — 날짜별 집계 가능)

## Analysis Steps
1. Aggregate sessions/users by channel_group for the range (descriptive only).
2. State the share each channel holds — and immediately flag that Direct dominance
   is a UTM-instrumentation artifact, not a real acquisition insight.
3. Report the UTM-unset caveat as the headline finding, not a footnote.

## Expected Output
```json
{
  "channel_mix": [{"channel": "...", "sessions": 0, "share_pct": 0.0, "engagement_rate": 0.0}],
  "trust": "LOW — UTM 미설정으로 채널 귀속 신뢰 불가",
  "recommended_action": "채널 결론 대신, 유입 링크에 UTM 파라미터부터 설정",
  "insight": "채널 우열 판단 금지 — 관측된 분포와 그 한계만 서술"
}
```

## QA Checklist
- Did the output state the UTM/LOW-trust caveat prominently (not buried)?
- Does it AVOID naming a "top" or "priority" channel or a channel-growth action?

## Anti-patterns
- Do NOT pick a top_quality_channel or priority channel — attribution is untrustworthy.
- Do NOT recommend shifting budget/effort toward any channel.
- Do NOT infer ad spend or ROAS (no cost data in mart).
- Do NOT merge channel data with Raw events.
