# Skill: journey_analysis

## Goal
Map the most common user navigation paths to understand how users explore the site before converting.

## Primary Owner
Data Scientist

## Input Mart
- journey_mart

## Analysis Steps
1. Retrieve top 10 from→to page path combinations by user count.
2. Identify paths that lead to the conversion page (/contact or /service).
3. Find "dead-end" paths (pages users leave from without progressing).
4. Calculate the most common entry → exit sequence.

## Expected Output
```json
{
  "top_paths": [{"from_page": "...", "to_page": "...", "users": 0}],
  "conversion_paths": ["..."],
  "dead_ends": ["..."],
  "insight": "..."
}
```

## Anti-patterns
- Do NOT infer purchase intent (B2B site, no e-commerce)
- Do NOT use Raw events for path reconstruction
