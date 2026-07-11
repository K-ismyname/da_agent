# Skill: dashboard_analysis

## Goal
Identify KPI trends and abnormal signals from the dashboard, and determine the analysis direction for the current question.

## Primary Owner
Product Analyst

## Input Mart
- dashboard_kpi

## Analysis Steps
1. Retrieve Users, Sessions, Page Views, Engagement Rate, Scroll Rate for the date range.
2. Calculate WoW (Week-over-Week) change for each KPI.
3. Flag any metric that changed more than ±10% as a signal.
4. Identify the top 1-2 metrics most relevant to the user's question.
5. Output analysis direction and KPI focus for downstream agents.

## Expected Output
```json
{
  "headline": "one-sentence summary of the most important finding",
  "kpis_focus": ["metric1", "metric2"],
  "signals": [{"metric": "...", "change_pct": 0.0, "direction": "up|down"}],
  "analysis_direction": "...",
  "goal": "what we need to verify in this analysis"
}
```

## QA Checklist
- Are all KPIs sourced from dashboard_kpi mart?
- Is WoW change calculated correctly (not YoY)?
- Is the headline actionable (not just descriptive)?

## Anti-patterns
- Do NOT fabricate KPI values not in the mart
- Do NOT write SQL directly — use mart service
- Do NOT define new KPIs outside of kpi_dictionary.md
