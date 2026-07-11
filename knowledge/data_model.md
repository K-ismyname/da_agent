# Data Model — Mart ERD

## BigQuery Dataset: formula_silk_analytics

### dashboard_kpi
| Column | Type | Description |
|---|---|---|
| date | DATE | event date |
| users | INT64 | daily unique users |
| sessions | INT64 | daily sessions |
| page_views | INT64 | daily page views |
| engagement_rate | FLOAT64 | engaged sessions / total sessions |
| scroll_rate | FLOAT64 | scroll events / page views |
| avg_engagement_time_sec | FLOAT64 | avg engaged time per session |
| returning_users | INT64 | users with >1 session |

### landing_page_mart
| Column | Type | Description |
|---|---|---|
| date | DATE | event date |
| page_path | STRING | URL path |
| page_views | INT64 | views per page |
| sessions | INT64 | sessions starting from this page |
| scroll_rate | FLOAT64 | scroll depth ratio |
| avg_engagement_time_sec | FLOAT64 | avg time on page |
| bounce_count | INT64 | single-page sessions |

### marketing_channel_mart
| Column | Type | Description |
|---|---|---|
| date | DATE | event date |
| channel_group | STRING | Organic/Direct/Social/Referral/etc. |
| sessions | INT64 | sessions from this channel |
| users | INT64 | users from this channel |
| engagement_rate | FLOAT64 | engagement rate by channel |

### funnel_mart
| Column | Type | Description |
|---|---|---|
| date | DATE | event date |
| funnel_step | STRING | Landing/Scroll/Engage/Convert |
| step_order | INT64 | step sequence number |
| users | INT64 | users at this step |
| drop_off_rate | FLOAT64 | % users who dropped at this step |

### journey_mart
| Column | Type | Description |
|---|---|---|
| date | DATE | event date |
| from_page | STRING | origin page path |
| to_page | STRING | destination page path |
| users | INT64 | users who took this path |
| sessions | INT64 | sessions with this path |

### cohort_mart
| Column | Type | Description |
|---|---|---|
| cohort_week | DATE | week user first visited |
| week_number | INT64 | weeks since first visit (0=acquisition) |
| users | INT64 | users retained this week |
| retention_rate | FLOAT64 | retained / cohort_size |

## Join Keys
- All marts join on `date`
- User-level joins: `user_pseudo_id` (Raw only — avoid in Mart queries)
- Session-level joins: `CONCAT(user_pseudo_id, '-', ga_session_id)` (Raw only)

## Mart Access Rules
- Services query marts via date range filter: `WHERE date BETWEEN @start AND @end`
- LIMIT always required for safety
- No subqueries joining Raw events_* with Mart tables
