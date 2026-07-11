# Skill: data_quality_check

## Goal
Verify that mart data is reliable and complete before analysis begins.

## Primary Owner
Analytics Engineer

## Input Mart
- All marts used in the current analysis

## Analysis Steps
1. Check for date gaps: are there missing dates in the requested range?
2. Check for null values in key metric columns.
3. Check for anomalies: values outside expected range (e.g., engagement_rate > 1).
4. Check record counts: are row counts reasonable vs. prior periods?
5. Flag any data quality issues found.

## Expected Output
```json
{
  "status": "pass|warn|fail",
  "issues": [{"mart": "...", "issue": "...", "severity": "high|medium|low"}],
  "date_coverage": {"expected_days": 0, "actual_days": 0},
  "recommendation": "proceed|investigate|halt"
}
```

## QA Checklist
- Were all input marts checked, not just one?
- Is the date range coverage verified?
- Is the recommendation actionable?

## Anti-patterns
- Do NOT skip this check because data "looks fine"
- Do NOT access Raw events_* to fix mart data
