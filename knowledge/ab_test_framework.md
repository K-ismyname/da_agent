# A/B Test Framework (Single Source of Truth)

> This document defines what counts as a valid A/B test in this project and how
> any experiment (existing or future) must be judged. `kpi_dictionary.md` defines
> individual metrics; this file defines the **methodology** that applies across
> all experiments regardless of which mart they live in.
> All agents and Skills must reference this file before designing or judging
> an A/B test. Do NOT invent a different significance rule or decision rule
> elsewhere in code or prompts.

---

## 1. Minimum requirements to call something an "experiment"

A dataset only qualifies for `run_significance_test` if it has, per row:
- **variant column**: exactly 2 distinct values (A/B). 3+ variants require a
  different test (not supported here — flag it instead of forcing a z-test).
- **numerator column**: count of "successes" for that group (e.g. `purchases`,
  `apply_reached`)
- **denominator column**: count of "exposure" for that group (e.g. `sessions`,
  `users_exposed`)
- **date column**: needed to track how much sample has accumulated and to
  scope the analysis window

If any of these is missing, do not fabricate a z-test — report `INSUFFICIENT_DATA`
instead.

## 2. Statistical standard

- **Test**: two-proportion z-test, computed deterministically in Python
  (`run_significance_test` in `tools/bigquery.py`) — never estimated by the LLM.
- **Significance threshold**: `p < 0.05` (95% confidence). Below this, treat the
  difference as noise regardless of how large the raw percentage gap looks.
- **Zero-denominator guard**: if either variant has 0 in the denominator, the
  test cannot run — report the error, do not divide by zero.
- **Minimum sample size (rule of thumb)**: before recommending a winner, check
  that each variant's denominator is large enough that a 1-count swing wouldn't
  flip the significance verdict. If sample is small (this project's real traffic
  often is — see `dashboard_kpi` date range), state that explicitly rather than
  presenting the result as final.

## 3. Primary vs Guardrail classification

- **Primary metric**: the metric that decides win/loss. Must be directly tied to
  this community's core goal (가입 전환 — `Community CVR` in kpi_dictionary.md),
  never a metric that only makes sense for a business model this community
  doesn't have (e.g. ad spend ROAS when no ads are running).
- **Guardrail metric**: a metric that must not regress by more than **10%**
  even if the Primary metric improves. Example: a signup-prompt banner might
  raise `/apply` reach (Primary) while also raising bounce rate (Guardrail) —
  both must be reported together.

## 4. Decision rule (applies to every experiment, not just Meta Ads)

> **Recommend variant B only if ALL Primary metrics favor B with p < 0.05,
> AND no Guardrail metric degrades by more than 10%.**
> Otherwise: `HOLD` (keep A) — do not recommend a change on a partial win.

This rule was previously only written inside the Data Scientist's A/B prompt
(`agents/nodes.py`). It is restated here so it is enforced the same way
regardless of which experiment is being judged.

## 5. Data requirements for a new experiment to be pluggable

To add a new experiment to `EXPERIMENT_METRICS` (`tools/bigquery.py`), its mart
must satisfy §1 exactly — same column shapes, different names. This is why
`signup_prompt_experiment_mart` (`variant`, `apply_reached`, `users_exposed`)
and `ab_test_mart` (`ab_variant`, `purchases`, `sessions`) can share the same
z-test code despite measuring completely different things.

## 6. Registered experiments

| experiment key | mart | status |
|---|---|---|
| `ab_test` | `ab_test_mart` | ⚠️ **합성·무관 데모** — Meta Ads 스터디 노트(JU_DATA)의 이커머스 예제. spend/CPC/CPM/add_to_cart 등은 이 커뮤니티(광고 미집행, 장바구니 없음)에 적용 불가. z-test 코드 재사용성 시연 용도로만 사용, 실제 성과로 발표 금지 |
| `signup_prompt` | `signup_prompt_experiment_mart` | 실제 커뮤니티 실험(설계 완료, 데이터는 아직 목업 — `build_signup_prompt_experiment_mart.py` 참고). 실기능(스크롤 배너) 배포 후 실데이터 VIEW로 교체 필요 |
| `home_sort` | `home_sort_experiment_mart` | 실제 커뮤니티 실험(설계 완료, 데이터는 아직 목업 — `build_home_sort_experiment_mart.py` 참고). ⚠️ 홈 상단 "인기 글 TOP 5" 위젯이 A/B 무관하게 항상 노출되어 있어, 하단 피드 정렬 변경의 실효과가 희석될 수 있음 — 실제 배포 시 이 한계를 같이 보고할 것. 실기능(middleware 리다이렉트) 배포 후 실데이터 VIEW로 교체 필요 |

Data Scientist는 질문에 맞는 experiment key를 **위 표에서 골라야 하며**, 등록 안 된
실험을 지어내거나 다른 실험 데이터로 대신 답해서는 안 된다(§4 결정 규칙과 별개로
지켜야 하는 선택 규칙).

New real experiments must be added to both this table and `EXPERIMENT_METRICS`,
following §5.

---
> Last updated: 2026-07-09
> Maintainer: Data Scientist Agent
