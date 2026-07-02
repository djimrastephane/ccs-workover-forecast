# Validation and Model QA

The Model QA tab in the dashboard provides a full validation audit. This document describes the validation framework.

---

## Calibration score

A composite score (0–100) that weights each assumption by `(source quality × confidence × sensitivity to output)`. High-sensitivity assumptions with expert-judgement or synthetic sources reduce the score.

- Score ≥ 80: Mature field — outputs suitable for engineering commitments.
- Score 60–79: Early operations — outputs suitable for FEED planning.
- Score 40–59: Pre-FEED — outputs are order-of-magnitude estimates.
- Score < 40: Concept study — outputs indicate relative risk only.

The current baseline calibration score is ~38/100 (Pre-FEED), accurately reflecting the state of CCS reliability knowledge as of 2026. This is expected and disclosed in the dashboard.

---

## Assumption quality register

Every parameter in `data/assumptions/assumption_quality.csv` is tagged with:

- **Source type**: OREDA (1.00) → literature (0.80) → operator_analogue (0.65) → expert_judgement (0.40) → synthetic_assumption (0.10)
- **Confidence level**: high / medium / low
- **Sensitivity level**: high / medium / low — how much the output changes when this parameter is varied ±30%

---

## Validation metrics

The dashboard runs the following sanity checks after each simulation:

| Metric | Normal range | Interpretation |
|---|---|---|
| Workovers per well per year | 0.05–0.5 | Outside range suggests implausible MTTF assumptions |
| Preventive fraction | 30–80% | Too low: monitoring underperforming; too high: threshold set too conservatively |
| Campaign average size | 2–20 wells | Very small campaigns may indicate `campaign_threshold` set too low |
| Emergency campaign fraction | 5–40% | Very high: safety barrier assumptions too pessimistic |
| P90/P50 cost ratio | 1.1–2.5 | Very wide: high assumption uncertainty; very narrow: assumptions may be overconfident |

---

## MTTF sensitivity tornado

An analytical one-at-a-time (OAT) sensitivity analysis is run after simulation. For each component, MTTF is varied from P10 to P90 while all others stay at mode. ΔCost is estimated analytically via the ratio of annual failure probabilities — no re-simulation required. Components with the widest swing are the top priorities for field calibration.

---

## Challenging the model

1. **Replace synthetic assumptions** — identify parameters flagged `synthetic_assumption` or `expert_judgement` with high sensitivity; these are the first targets for data collection.
2. **Calibrate against field data** — compare simulated `workovers_per_well` in Model QA against observed rates; adjust P10/P90 MTTF values in `component_failure_assumptions.csv` until P50 matches the historical mean.
3. **Stress-test critical gaps** — vary packer and cement MTTF P10 values by ±30%; if the cost range exceeds 2×, calibration is essential before using outputs for CAPEX decisions.
4. **Validate campaign logic** — compare Model QA → Campaign Frequency and Average Campaign Size against historical operator campaign records.
5. **Apply to a specific asset** — replace `scenario_config.csv` with asset-specific failure probability multiplier, offshore flag, and SCSSV configuration.
