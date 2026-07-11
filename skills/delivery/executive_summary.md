# Skill: executive_summary

## Goal
Generate the AI Executive Brief — a concise, actionable summary for the dashboard hero section.

## Primary Owner
Head of Data

## Input
- report_writer output
- QA verdict + Confidence Score
- All agent key findings

## Analysis Steps
1. Distill to ONE headline sentence (the most important finding).
2. List top 3 insights (each with a supporting metric).
3. List top 2 recommended actions.
4. Flag business risks if any findings are concerning.
5. Include Confidence Score and QA Verdict prominently.

## Expected Output
```json
{
  "headline": "...",
  "insights": [{"text": "...", "metric": "...", "value": "..."}],
  "recommendations": [{"action": "...", "rationale": "..."}],
  "risks": ["..."],
  "confidence_score": 0,
  "qa_verdict": "PASS|WARN|FAIL"
}
```

## Anti-patterns
- Do NOT write more than 3 insights (keep it executive-level)
- Do NOT include raw numbers without business context
