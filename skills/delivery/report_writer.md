# Skill: report_writer

## Goal
Write the Executive Report in markdown format that summarizes the full analysis for decision-makers.

## Primary Owner
BI Analyst

## Input
- All validated agent outputs
- QA verdict + Confidence Score

## Analysis Steps
1. Write a 1-paragraph executive summary (the "so what").
2. List 3-5 key findings with supporting data.
3. List 2-3 recommended actions with business rationale.
4. Include data trust disclaimer if confidence < 70%.
5. Format as clean markdown suitable for PDF export.

## Expected Output
Markdown document with sections:
- ## Executive Summary
- ## Key Findings
- ## Recommendations
- ## Data Quality Note (if confidence < 70%)
- ## Analysis Details (evidence from each agent)

## Anti-patterns
- Do NOT write findings not supported by evidence
- Do NOT omit data quality warnings when confidence is low
