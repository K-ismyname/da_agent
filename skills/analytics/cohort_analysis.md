# Skill: cohort_analysis

## Goal
Analyze user retention by cohort to understand how well the product retains visitors week over week.

## Primary Owner
Data Scientist

## Input Mart
- cohort_mart

## Analysis Steps
1. Retrieve cohort retention data grouped by cohort_week and week_number.
2. Calculate Week 1 retention rate (most important benchmark).
3. Compare W1 retention across the last 4 cohorts.
4. Identify if retention is improving or declining over time.
5. Flag the cohort with unusually high or low retention.

## Expected Output
```json
{
  "cohorts": [{"cohort_week": "...", "week_0_users": 0, "week_1_retention": 0.0}],
  "avg_w1_retention": 0.0,
  "trend": "improving|stable|declining",
  "best_cohort": "...",
  "worst_cohort": "...",
  "insight": "..."
}
```

## QA Checklist
- Is retention_rate between 0 and 1?
- Are cohort weeks non-overlapping?
- Is week_0 always = acquisition week?

## Anti-patterns
- Do NOT define "returning user" differently from kpi_dictionary.md
- Do NOT use Raw events for cohort construction
