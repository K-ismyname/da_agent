# Skill: visualization

## Goal
Determine the best chart type for each data pattern and provide visualization configuration.

## Primary Owner
BI Analyst

## Input
- dashboard_builder output

## Analysis Steps
1. For KPI trends → Line chart (time series).
2. For channel mix → Donut/Pie chart.
3. For funnel steps → Horizontal bar chart (descending).
4. For journey paths → Sankey or table.
5. For cohort retention → Heatmap (week × cohort).
6. Output Chart.js-compatible config for each.

## Expected Output
```json
{
  "charts": [
    {"id": "kpi_trend", "type": "line", "config": {}},
    {"id": "channel_mix", "type": "doughnut", "config": {}},
    {"id": "funnel", "type": "bar", "config": {}}
  ]
}
```
