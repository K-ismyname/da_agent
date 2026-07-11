# Skill: journey_analysis

## Goal
Map the most common user navigation paths to understand how members explore the
community (아티클 소비 → 가입) and where sessions dead-end before converting.

## Primary Owner
Data Scientist

## Input Mart
- journey_mart — columns: `path` (한 세션의 페이지 이동을 "A → B → C" 문자열로 이은 값),
  `sessions` (그 경로를 밟은 세션 수). from_page/to_page 컬럼은 없다 — 경로는 문자열 하나다.

## Analysis Steps
1. Retrieve top paths ordered by `sessions` (most common navigation flows).
2. Identify paths that end at the conversion signal (`/onboarding`, 가입 완료) —
   which entry points and content actually lead to a join.
3. Find "dead-end" paths (세션이 아티클/아카이브에서 멈추고 `/apply`로 못 넘어가는 흐름).
4. Note the most common entry page (경로 첫 토큰) and whether it matches the site's
   intended landing (`/` 메인 피드).

## Expected Output
```json
{
  "top_paths": [{"path": "/ → /article/... → /apply", "sessions": 0}],
  "conversion_paths": ["가입 완료(/onboarding)로 이어진 경로"],
  "dead_ends": ["가입으로 못 넘어가고 끝난 흔한 경로"],
  "insight": "..."
}
```

## QA Checklist
- Are paths ranked by actual `sessions` count from the mart (not invented)?
- Is the conversion signal `/onboarding` (not a non-existent /contact or /service)?

## Anti-patterns
- Do NOT reference pages this site doesn't have (no /contact, /service, checkout).
- Do NOT infer purchase/e-commerce intent — this is a free-signup community, not e-commerce.
- Do NOT use Raw events_* for path reconstruction — journey_mart only.
