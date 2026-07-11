# Skill: ab_test_analysis

## Goal
Compare this community's REGISTERED A/B experiments using the industry-standard
frame: Primary metric decides GO/NO-GO, Guardrail metric protects against side
effects. This skill is experiment-agnostic — the registry decides the mart/columns,
this document decides the procedure.

> ⚠️ 이 스킬은 `ab_test_mart`(Meta Ads×GA4 스터디 노트, 광고비/장바구니 지표)를
> 쓰지 않는다. 그 마트는 이 커뮤니티와 무관한 데모 자료다(`ab_test_framework.md`
> §6 참고). 실제로 쓰는 실험은 `EXPERIMENT_METRICS`에 `"real": true`로 등록된
> 것들뿐이다(현재: `signup_prompt`, `home_sort`).

## Primary Owner
Data Scientist

## Input
- 어느 마트를 볼지는 하드코딩하지 않는다. 질문에 맞는 실험 이름을
  `EXPERIMENT_METRICS`(등록된 real 실험 목록, 시스템 프롬프트에 설명 포함)에서
  골라 `get_experiment_summary(experiment=...)`/`run_significance_test(experiment=...)`
  에 그대로 넘긴다.
- 질문이 어느 등록 실험과도 안 맞으면 **지어내지 말고** root_cause에 그 사실을 적고 멈춘다.

## Metric Frame (definitions in knowledge/kpi_dictionary.md)
- **Primary**: 그 실험의 `numerator_col / denominator_col` 비율 → decides the winner
- **Guardrail**: 그 실험에 `guardrail_col`이 있으면 `guardrail_col / denominator_col` 비율
  → must not degrade >10% (guardrail이 없는 실험은 이 항목을 생략)

## Analysis Steps
1. 질문에서 어느 등록 실험을 말하는지 판단 (예: "배너"→signup_prompt, "정렬"→home_sort).
2. Get date range and both variants for that experiment; confirm equal coverage.
3. Aggregate per variant using `get_experiment_summary(experiment=...)` — never
   per-row averages, never a different experiment's mart.
4. Compute Primary rate per variant + Lift % = (B − A) / A × 100.
5. Run statistical significance test using `run_significance_test(experiment=...)`
   (same experiment name, two-proportion z-test). NEVER estimate a p-value yourself.
6. If the experiment has a Guardrail column, compute it per variant; flag if B is >10% worse.
7. Report absolute counts too, not only rates (10% lift on 10 users ≠ 10% lift on 10,000).
8. State current sample size explicitly — this community's real traffic is small,
   so note if the result should be treated as directional rather than final.
9. Verdict rule (from `ab_test_framework.md` §4): recommend B only if Primary rate
   favors B with significance AND Guardrail (if any) is not >10% worse. Otherwise HOLD.

## Expected Output
```json
{
  "experiment": "the registered experiment name you picked",
  "period": {"start": "...", "end": "..."},
  "primary_metrics": [{"metric": "실제 지표명", "a": 0.0, "b": 0.0, "lift_pct": 0.0, "significant": true, "p_value": 0.0}],
  "guardrail_metrics": [{"metric": "실제 지표명", "a": 0.0, "b": 0.0, "verdict": "OK|DEGRADED"}],
  "recommended_variant": "A|B|HOLD",
  "rationale": "...",
  "sample_size_caveat": "...",
  "next_actions": ["..."]
}
```

## QA Checklist
- Did you pick the experiment name that actually matches the question (not a default)?
- Does Primary/Guardrail rate come from mart sums (not per-row averages)?
- Is p-value from the significance tool, not the LLM?
- Is Guardrail reported even when Primary favors B (if the experiment has one)?
- Are absolute counts shown alongside rates?
- Is the sample-size caveat stated when denominators are small?

## Anti-patterns
- Do NOT default to `signup_prompt` when the question is about a different experiment
- Do NOT declare a winner from the Primary metric alone (check Guardrail)
- Do NOT average daily rates (aggregate numerators/denominators first)
- Do NOT pull spend/CPC/ROAS/add_to_cart from `ab_test_mart` into this analysis —
  that mart measures an unrelated e-commerce study dataset, not this community
- Do NOT fabricate p-values or confidence intervals
