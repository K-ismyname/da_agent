# Skill: funnel_analysis

## Goal
Analyze the community join funnel (방문 → 콘텐츠 소비 → 가입 페이지 도달(/apply) → 로그인/가입 시도(/account) → 가입 완료(/onboarding)) to find the biggest drop-off step. funnel_mart is grained by cohort_date (user's first-visit day), so per-date funnel comparison is possible.

## Primary Owner
Data Scientist

## Input Mart
- funnel_mart
- landing_page_mart (for landing step details)

## Analysis Steps
1. Retrieve all funnel steps ordered by step_order for the date range.
2. Calculate users at each step and drop-off rate between steps.
3. Identify the step with the highest drop-off rate (worst bottleneck).
4. Compare with prior period — is the bottleneck getting worse or better?
5. Correlate worst-step with landing page performance if applicable.

## Expected Output
```json
{
  "funnel_steps": [{"step": "...", "users": 0, "drop_off_rate": 0.0}],
  "worst_step": {"step": "...", "drop_off_rate": 0.0},
  "wow_change": {"step": "...", "change_pct": 0.0},
  "insight": "...",
  "recommendation": "..."
}
```

## QA Checklist
- Do users at each step decrease monotonically (or flag if not)?
- Is worst_step backed by actual drop_off_rate data?
- Is the period correct (requested date range)?

## Anti-patterns
- Do NOT use Raw events_* for funnel construction
- Do NOT fabricate conversion rates not in mart
