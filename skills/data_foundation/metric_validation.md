# Skill: metric_validation

## Goal
Validate that metrics used in analysis are correctly scoped, granulated, and refreshed per metric_definition.md.

## Primary Owner
Analytics Engineer

## Input
- knowledge/metric_definition.md
- Metrics referenced by other agents in this analysis

## Analysis Steps
1. List all metrics used in the current analysis pipeline.
2. For each metric, verify: Purpose matches claim, Grain matches aggregation, Refresh cycle matches date range.
3. Flag any metric used at wrong grain (e.g., using daily metric for weekly comparison).

## Expected Output
```json
{
  "metrics_used": ["..."],
  "validation_results": [{"metric": "...", "grain_ok": true, "refresh_ok": true, "note": "..."}],
  "overall_status": "pass|warn"
}
```
