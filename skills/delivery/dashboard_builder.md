# Skill: dashboard_builder

## Goal
Structure analysis results into a dashboard-ready JSON format for the Executive Dashboard UI.

## Primary Owner
BI Analyst

## Input
- All validated agent outputs
- QA Reviewer verdict

## Analysis Steps
1. Organize KPI summary (Users, Sessions, Engagement Rate, Scroll Rate + WoW changes).
2. Structure channel breakdown data for pie/bar chart rendering.
3. Format funnel data as step-by-step array for funnel visualization.
4. Format journey paths as flow data.
5. Format cohort data as retention heatmap data.
6. Compile AI Executive Brief (headline + key insights + recommendations).

## Expected Output
```json
{
  "kpi_summary": {"users": 0, "sessions": 0, "engagement_rate": 0.0, "wow": {}},
  "channel_data": [{"channel": "...", "sessions": 0, "share": 0.0}],
  "funnel_data": [{"step": "...", "users": 0, "drop_off": 0.0}],
  "journey_data": [{"from": "...", "to": "...", "users": 0}],
  "cohort_data": [{"week": "...", "retention": []}]
}
```

## Anti-patterns
- Do NOT generate data not returned by upstream agents
- Do NOT modify QA-validated numbers
