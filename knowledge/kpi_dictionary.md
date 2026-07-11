# KPI Dictionary (Single Source of Truth)

> This document is the **SSOT** for all KPI definitions used by AI agents.
> All agents and Skills must reference this file before defining any metric.
> Do NOT redefine KPIs elsewhere in code or prompts.

---

## Users
- **Business Definition**: unique visitors to the site (logged-in users)
- **SQL Definition**: `COUNT(DISTINCT user_pseudo_id)`
- **Calculation**: use `dashboard_kpi.users` — same-day deduplication (multiple visits = 1 user)
- **Source Mart**: `dashboard_kpi`
- **Owner**: Analytics Engineer
- **Notes**: based on `user_pseudo_id` (device/browser basis), not login-based count

## Sessions
- **Business Definition**: number of new visits (each fresh visit counts separately)
- **SQL Definition**: `COUNT(DISTINCT CONCAT(user_pseudo_id, '-', ga_session_id))`
- **Calculation**: mart `dashboard_kpi.sessions`
- **Source Mart**: `dashboard_kpi`
- **Owner**: Analytics Engineer

## Page Views
- **Business Definition**: total page view count
- **SQL Definition**: `COUNT(*) WHERE event_name = 'page_view'`
- **Source Mart**: `dashboard_kpi`
- **Owner**: Analytics Engineer

## Engagement Rate
- **Business Definition**: ratio of engaged sessions (scroll, click, conversion intent)
- **SQL Definition**: `engaged_sessions / total_sessions`
- **Source Mart**: `dashboard_kpi`
- **Notes**: GA4 standard definition — session duration > 10s OR 2+ page views OR conversion

## Scroll Rate
- **Business Definition**: ratio of users who scrolled on landing page
- **SQL Definition**: `scroll_events / page_view_events`
- **Source Mart**: `landing_page_mart`
- **Owner**: Product Analyst

## Returning Users
- **Business Definition**: users who visited more than once in the period
- **SQL Definition**: users with session_count > 1
- **Source Mart**: `cohort_mart`
- **Owner**: Data Scientist

## Community CVR (Conversion Rate)
- **Business Definition**: share of visitors who complete the join (커뮤니티 가입 전환율)
- **SQL Definition**: `가입 완료 users / 방문 users` (unique user basis)
- **Source Mart**: `funnel_mart` — `가입 완료` row users ÷ `방문` row users
- **Owner**: Data Scientist
- **Notes**: North Star Metric. A/B Test CVR(purchases/sessions)와 혼용 금지.
  `form_submit` 이벤트 기반 아님 — `/apply`에 `<form>` 태그가 없어(소셜 로그인만)
  page_view 경로(`/onboarding` 도달)로 가입 완료를 판정한다.

## Community Funnel Steps
- **Definition** (5 steps, 2026-07-09 재설계): 방문 → 콘텐츠 소비(page_view+scroll)
  → 가입 페이지 도달(`/apply`) → 로그인/가입 시도(`/account`) → 가입 완료(`/onboarding`)
- **Grain**: `funnel_mart`는 `cohort_date`(유저 첫 방문일)별로 5단계를 집계 — 날짜별 퍼널 비교 가능
- **Drop-off rate**: `1 - (step_n users / step_(n-1) users)`, `funnel_mart.drop_off_rate` 컬럼에 사전 계산됨
- **Source Mart**: `funnel_mart`
- **Notes**: `/account`·`/onboarding`의 의미는 실측 트래픽 기반 추정(서비스 담당 확인 필요).

## Channel Attribution
- **Business Definition**: session source by traffic channel (Organic/Direct/Social/etc.)
- **Dimension**: source/medium → grouped channel
- **Source Mart**: `marketing_channel_mart`
- **Owner**: Data Scientist
- **⚠️ 신뢰도 LOW**: UTM 파라미터 미설정으로 현재 모든 트래픽이 Direct 집계.
  채널 분석 시 반드시 "UTM 미설정으로 채널 데이터 신뢰 불가" 경고 출력.
  채널 수치를 근거로 결론 도출 금지.

---

# A/B Test KPIs — 이 커뮤니티의 실제 실험 (`signup_prompt_experiment_mart`)

> 가입 유도 배너 실험(A: 저장/댓글/팔로우 시도 시 수동 노출, B: 스크롤 90% 시점
> 능동 노출)의 지표. 방법론은 `knowledge/ab_test_framework.md`가 SSOT.

## Apply Reach Rate — PRIMARY
- **Business Definition**: 배너 트리거 조건에 노출된 사용자 중 `/apply` 도달 비율
- **SQL Definition**: `SUM(apply_reached) / SUM(users_exposed)`
- **Source Mart**: `signup_prompt_experiment_mart`
- **Owner**: Data Scientist

## Bounce Rate — GUARDRAIL
- **Business Definition**: 트리거 노출 직후 이탈한 비율 (배너가 방해 요소인지)
- **SQL Definition**: `SUM(bounced) / SUM(users_exposed)`
- **Source Mart**: `signup_prompt_experiment_mart`
- **Notes**: B가 A보다 10% 이상 악화되면 승자 판정 무효

## Banner CTR — INFO (B-only)
- **Business Definition**: 배너가 노출된 사람 중 클릭한 비율
- **SQL Definition**: `SUM(banner_click) / SUM(banner_shown)`
- **Source Mart**: `signup_prompt_experiment_mart`
- **Notes**: A는 배너 자체가 없어 항상 NULL/0. 승자 판정에는 사용하지 않음

---

# ⚠️ 무관한 데모 자료 (Meta Ads × GA4 — `ab_test_mart` only)

> 이 섹션의 지표는 이 커뮤니티와 **무관한 합성 스터디 자료**(JU_DATA Meta Ads
> Study Note)를 그대로 가져온 것이다. 광고를 집행하지 않고 장바구니도 없는
> 이 서비스에는 적용 불가 — z-test 코드 재사용성 시연 용도로만 남겨두며,
> 실제 성과로 발표·인용 금지.

## CVR (Conversion Rate) — DEMO ONLY
- **SQL Definition**: `SUM(purchases) / SUM(sessions)` (GA4 attribution)
- **Source Mart**: `ab_test_mart`

## ROAS (Return on Ad Spend) — DEMO ONLY
- **SQL Definition**: `SUM(revenue) / SUM(spend)` (revenue: GA4, spend: Meta)
- **Source Mart**: `ab_test_mart`

## Cost per Purchase / CPC / CPM / Cost per Add-to-Cart — DEMO ONLY
- **Source Mart**: `ab_test_mart`
- **Notes**: spend·clicks·impressions·add_to_carts 컬럼 전부 무관한 이커머스 예제 데이터

---

## ⚠️ Metrics NOT defined here
The following CANNOT be measured with current marts and must NOT be fabricated:
- Purchase/revenue for non-A/B-test traffic (e-commerce events exist only in ab_test_mart)
- Email open rates (not tracked in GA4)
- App-specific metrics

---
> Last updated: 2026-07-02
> Maintainer: Analytics Engineer Agent
