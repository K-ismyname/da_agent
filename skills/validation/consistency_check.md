# Skill: consistency_check

## Goal
Ensure all agents in the pipeline reached consistent conclusions — no contradictions between agent outputs.

## Primary Owner
QA Reviewer

## Input
- All agent outputs in the current analysis session

## Analysis Steps
1. Collect the key conclusions from each agent.
2. Compare same-metric values cited by different agents — flag discrepancies >2%.
3. Check that overlapping date ranges use the same data.
4. Identify any logical contradictions (e.g., Agent A says traffic increased, Agent B says it decreased).
5. Produce consistency verdict.

## Expected Output
```json
{
  "consistency_status": "pass|warn|fail",
  "discrepancies": [{"metric": "...", "agent_a": "...", "agent_b": "...", "delta": 0.0}],
  "contradictions": ["..."],
  "verdict": "consistent|inconsistent"
}
```

## Anti-patterns
- Do NOT resolve contradictions by choosing one agent's answer arbitrarily
- Do NOT skip agents that didn't run (mark as N/A)
