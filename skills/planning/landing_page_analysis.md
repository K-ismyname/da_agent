# Skill: landing_page_analysis

## Goal
Analyze landing page performance to identify which pages drive engagement and which pages need improvement.

## Primary Owner
Product Analyst

## Input Mart
- landing_page_mart

## Analysis Steps
1. Rank pages by page_views for the date range.
2. For each top page, calculate scroll_rate and avg_engagement_time_sec.
3. Compare scroll_rate vs. site average — flag pages below average.
4. Identify the highest-traffic page with the lowest engagement (optimization candidate).
5. Note WoW changes for top 5 pages.

## Expected Output
```json
{
  "top_pages": [{"page_path": "...", "views": 0, "scroll_rate": 0.0, "engagement_time_sec": 0}],
  "low_engagement_pages": ["..."],
  "optimization_candidate": "page_path",
  "insight": "..."
}
```

## QA Checklist
- Is landing_page_mart the only source used?
- Are scroll_rate values between 0 and 1?
- Is the optimization candidate backed by data (not assumption)?

## Anti-patterns
- Do NOT use Raw events_* to get page data
- Do NOT infer user intent beyond what scroll/time data shows
