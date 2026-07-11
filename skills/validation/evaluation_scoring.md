# Skill: evaluation_scoring

## Goal
Score the reliability of the full analysis output using the evaluation frame:
Confidence, Hallucination Risk, Grounded.Numeric, Grounded.LLM → QA Verdict.

## Primary Owner
QA Reviewer (evaluation node)

## Inputs
- All agent outputs (data_scientist, bi_analyst drafts)
- Mart data actually queried during the run (evidence)

## Metric Definitions
| Metric | Purpose | Formula |
|---|---|---|
| Grounded.Numeric | Do cited numbers match mart data? | matched / total numeric claims × 100 (tolerance ±2%) |
| Grounded.LLM | Are statements supported by data? | LLM judge: YES=1, PARTIAL=0.5, NO=0 → mean × 100 |
| Hallucination Risk | Chance of ungrounded claims | 100 − (Grounded.Numeric + Grounded.LLM) / 2 |
| Confidence | Overall trust in the analysis | (PASS + PARTIAL × 0.5) / total checks × 100 |
| QA Verdict | Final gate | Rule-based: see below |

## Verdict Rules
- PASS: Confidence ≥ 70 AND Hallucination Risk ≤ 30
- WARN: Confidence ≥ 50 AND Hallucination Risk ≤ 50
- FAIL: otherwise → pipeline must stop (Head of Data cannot publish)

## Steps
1. Extract every numeric claim from analysis outputs.
2. Compare each against mart evidence → PASS / PARTIAL (within ±2%) / FAIL.
3. LLM-judge every qualitative statement against evidence → YES / PARTIAL / NO.
4. Compute the four scores with the formulas above (in code, not by LLM).
5. Apply verdict rules. Record an investigation log: which checks ran,
   which evidence was used, why the verdict was reached.

## Anti-patterns
- Do NOT let the LLM compute the final scores (deterministic code only)
- Do NOT skip scoring when the analysis "looks right"
- Do NOT count the same number twice (dedupe claims)
