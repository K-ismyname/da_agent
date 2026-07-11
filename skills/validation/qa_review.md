# Skill: qa_review

## Goal
Validate that all numeric claims in the analysis are grounded in mart data and logically consistent.

## Primary Owner
QA Reviewer

## Input
- Results from all upstream agents (Product Analyst, Analytics Engineer, Data Scientist)
- Mart data (for numeric verification)

## Analysis Steps
1. Extract all numeric claims from agent outputs.
2. For each claim, verify the value exists in the referenced mart (Grounded.Numeric check).
3. Run LLM judge to verify the claim language matches the data (Grounded.LLM check).
4. Apply rule-based scoring:
   - PASS: claim verified in mart + language accurate
   - PARTIAL: claim directionally correct but imprecise
   - FAIL: claim not found in mart or contradicts data
5. Calculate Confidence Score: (PASS + PARTIAL×0.5) / total_claims × 100
6. Calculate Hallucination Risk: 100 - (Grounded.Numeric + Grounded.LLM) / 2
7. Produce QA Verdict: PASS (>80%) / WARN (60-80%) / FAIL (<60%)

## Expected Output
```json
{
  "claims_checked": 0,
  "grounded_numeric": 0.0,
  "grounded_llm": 0.0,
  "confidence_score": 0,
  "hallucination_risk": 0,
  "qa_verdict": "PASS|WARN|FAIL",
  "data_trust": "high|medium|low",
  "flagged_claims": [{"claim": "...", "verdict": "PARTIAL|FAIL", "reason": "..."}]
}
```

## Anti-patterns
- Do NOT skip claims that seem obvious
- Do NOT pass analysis with FAIL verdict without flagging
- Do NOT modify upstream agent outputs — only validate
