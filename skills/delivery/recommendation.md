# Skill: recommendation

## Goal
Generate prioritized action items based on the full analysis, ranked by business impact.

## Primary Owner
Head of Data

## Input
- executive_summary output
- All agent findings

## Analysis Steps
1. List all potential actions surfaced by any agent.
2. Score each action by: impact (H/M/L) × effort (H/M/L) × confidence (0-100).
3. Rank top 3 actions by impact/effort ratio.
4. For each action: specify owner, success metric, and target timeline.

## Expected Output
```json
{
  "actions": [
    {
      "action": "...",
      "impact": "high|medium|low",
      "effort": "high|medium|low",
      "owner": "...",
      "success_metric": "...",
      "timeline": "..."
    }
  ],
  "priority_action": "..."
}
```
