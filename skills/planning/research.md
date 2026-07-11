# Skill: research

## Goal
Investigate background context, benchmarks, or business logic needed before or during analysis.

## Primary Owner
Product Analyst

## Input
- knowledge/business_context.md
- knowledge/kpi_dictionary.md
- User question context

## Analysis Steps
1. Review business_context.md for relevant service/product context.
2. Check kpi_dictionary.md to confirm which KPIs are measurable.
3. Identify any assumptions that need validation.
4. Summarize what is known vs. what needs data to confirm.

## Expected Output
```json
{
  "context_summary": "...",
  "measurable_kpis": ["..."],
  "assumptions": ["..."],
  "data_gaps": ["..."]
}
```

## Anti-patterns
- Do NOT fabricate benchmarks not present in knowledge files
- Do NOT define KPIs outside kpi_dictionary.md
