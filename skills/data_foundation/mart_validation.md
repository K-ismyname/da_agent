# Skill: mart_validation

## Goal
Confirm that mart KPI values match their definitions in kpi_dictionary.md.

## Primary Owner
Analytics Engineer

## Input Mart
- dashboard_kpi
- knowledge/kpi_dictionary.md

## Analysis Steps
1. Pull a sample of KPI values from the mart (last 7 days).
2. Cross-check each KPI definition against kpi_dictionary.md.
3. Flag any metric that appears inconsistent with its definition.
4. Confirm mart schema matches data_model.md.

## Expected Output
```json
{
  "validation_status": "pass|warn|fail",
  "kpi_checks": [{"kpi": "...", "status": "pass|fail", "note": "..."}],
  "schema_match": true
}
```

## Anti-patterns
- Do NOT redefine KPIs during validation
- Do NOT modify mart data
