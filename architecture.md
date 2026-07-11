# AI Data Team OS — Full Architecture

## Data Flow
```
GA4
 └─ (admin batch SQL — Raw only here)
BigQuery Raw: analytics_XXXXXXX.events_*
 └─
BigQuery Mart: demo_ga4_mart
     ├── dashboard_kpi
     ├── landing_page_mart
     ├── marketing_channel_mart
     ├── funnel_mart
     ├── journey_mart
     └── cohort_mart
         └─ services/* (Mart SELECT + date filter) ← Raw direct access FORBIDDEN

── /api/analyze (Server) ─────────────────────────────────────────────────────┐
│  knowledge/kpi_dictionary + business_context → (prompt injection, SSOT)    │
│                                                                              │
│  ○ Planner (lib/planner): question → select required Skills only           │
│     ▼ Dynamic Skill Selection (maintain fixed order, select needed only)    │
│  ○ Product → Engineer → Scientist → QA → BI → Head  (lib/agents)           │
│     each Agent = agent.md + selected skill.md + mart + peer analysis        │
│     (0 skills = skip / QA·Head always run)                                  │
│     Claude tool-use (structured JSON)                                       │
│  ○ Confidence calculation (session·QA·trust·consistency)                   │
│  ○ Evidence collection   Investigation Log                                  │
│  ○ Stop Hook → Executive Report(md) → PDF(downloads/)                      │
└─────────────────────────────────────────────────────────────────────────────┘
 ▼
JSON { brief · evidence · investigationLog · confidence · roles · report · data · kpiSummary }
 ▼
Executive Dashboard (app/page.tsx — React/Tailwind/Chart.js) ← API JSON only
  Question input → ①AI Executive Brief → ②Evidence Cards → ③Investigation Timeline
               → ④Supporting Dashboard(KPI·Channel·Landing·Funnel·Journey·Cohort) → ⑤AI Team Activity

Left sidebar 5 tabs: Dashboard · Ask Your Data · Knowledge Base · Skill Library · AI Team

## Separate Flow — Ask Your Data (Query mode)
Question → /api/ask → queryPlanner(KPI Dict + Data Model, NL→SQL)
         → sqlSafety(SELECT only, LIMIT required, Raw forbidden)
         → BigQuery run → Claude interpret → result + SQL + AI interpretation
         (Raw events_* forbidden in this raw mode too)

## Core Principles (all layers)
- Mart only · Raw = mart generation SQL + ask raw mode only
- Agents never write SQL · Skills = method only · KPI = Dictionary SSOT
- Dashboard renders API results only · AI does NOT generate data
- All results validated by QA Reviewer · certification server-side only
```

## Key Files
```
knowledge/kpi_dictionary.md      ← SSOT: all KPI definitions
knowledge/business_context.md   ← service/product/customer context
knowledge/data_model.md          ← mart ERD + join keys
knowledge/metric_definition.md  ← metric Purpose·Grain·Refresh

skills/ (17)                     ← reusable analysis modules
agents/ (6)                      ← role personas with Do/Don't
config/workflows.yaml            ← execution order + skill assignment
lib/planner.ts                   ← question → skill selection
lib/agents.ts                    ← 6-agent pipeline runner
lib/bigquery.ts                  ← BQ client + getAllMarts + dryRun
lib/claude.ts                    ← Claude tool-use (structured JSON)
lib/hooks.ts                     ← Stop Hook: report/pdf/slack

services/dashboard.ts            ← dashboard_kpi mart queries
services/landing.ts              ← landing_page_mart queries
services/funnel.ts               ← funnel_mart queries
services/journey.ts              ← journey_mart queries
services/cohort.ts               ← cohort_mart queries
services/channel.ts              ← marketing_channel_mart queries
services/queryPlanner.ts         ← NL → SQL planner
services/sqlSafety.ts            ← query guardrail
services/bigqueryAsk.ts          ← Ask Your Data engine

app/api/analyze/route.ts         ← main analysis endpoint
app/api/ask/route.ts             ← ask your data endpoint
app/api/data/route.ts            ← mart data fetch
app/api/report/route.ts          ← PDF/MD download
app/page.tsx                     ← SaaS 5-tab layout
```
