# Skill: marketing_channel_analysis

## Goal
Analyze traffic channel mix and identify which channels drive the most quality sessions.

## Primary Owner
Data Scientist

## Input Mart
- marketing_channel_mart

## Analysis Steps
1. Aggregate sessions and users by channel_group for the date range.
2. Calculate each channel's share of total sessions (%).
3. Compare engagement_rate by channel — rank channels by quality.
4. Calculate WoW change per channel.
5. Identify the channel with highest volume + highest engagement (priority channel).
6. Flag channels with declining share or engagement.

## Expected Output
```json
{
  "channel_mix": [{"channel": "...", "sessions": 0, "share_pct": 0.0, "engagement_rate": 0.0}],
  "top_quality_channel": "...",
  "declining_channels": ["..."],
  "wow_changes": [{"channel": "...", "sessions_change_pct": 0.0}],
  "insight": "..."
}
```

## QA Checklist
- Do channel shares sum to ~100%?
- Is engagement_rate between 0 and 1?
- Is WoW based on same day-of-week comparison?

## Anti-patterns
- Do NOT infer ad spend or ROAS (no cost data in mart)
- Do NOT merge channel data with Raw events
