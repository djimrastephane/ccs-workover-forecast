# Field Calibration

As CCS fields accumulate operational history, observed failure rates should replace literature-derived MTTF assumptions. The calibration engine in `src/field_calibration.py` does this automatically.

---

## How it works

```
Expected failures  = Σ base_rate × bathtub_mult(t)   [summed over all observed well-years]
Calibration factor = observed_failures / expected_failures
Confidence         = min(n_observed / 20, 1.0)
Effective factor   = 1 + confidence × (calibration_factor − 1)
Calibrated MTTF    = base_MTTF / effective_factor
```

where `base_rate = 1 − exp(−1 / mode_MTTF)` and `bathtub_mult(t)` is the component's own lifecycle multiplier for year *t* — the standard bathtub curve for mechanical components (1.5× infant mortality years 1–2; 1.0× useful life; ramping to 1.8× wear-out over the final 30% of design life), or the component's `lifecycle_shape` (infant / plateau / wear_out) for the geochemical injectivity sub-modes. The exposure sum is computed per shape, so an early-life observation window weights an infant-shaped sub-mode's expected count correctly.

---

## Bathtub weighting

Bathtub weighting ensures the expected count reflects the actual lifecycle phase mix of the observation window. Without it, an observation window dominated by early-life years would inflate the calibration factor — falsely attributing normal infant-mortality failures to MTTF underestimation, causing double-counting when the simulation applies the same multiplier.

---

## Confidence weighting

The confidence weighting prevents a single observed event from rewriting assumptions — at 1 event the effective factor shifts only 5% of the way toward the calibration factor; at 20+ events it fully converges.

---

## Adding field data

Append rows to `data/observations/observed_events.csv`:

| Column | Description |
|---|---|
| `field_id` | Field identifier (e.g. `FIELD_A`) |
| `well_id` | Well identifier |
| `component` | Must match a component in `component_failure_assumptions.csv` |
| `install_year` | Year the component was installed |
| `event_year` | Year of failure / degradation |
| `event_type` | `failure` or `degradation` (counted for calibration); `inspection` or `maintenance` (informational only) |

Then select the field in the sidebar **Reference Field** selector. The model automatically applies calibrated MTTF values before running the simulation.

---

## Reliability Maturity Score

Displayed in the Field Calibration tab (0–100). Combines:

- Years of operational history (30%)
- Observed event count (30%)
- Component coverage (20%)
- Mean calibration confidence (20%)

Levels: Concept study → Pre-FEED → FEED → Early operations → Mature field.

---

## Drift alerts

Drift alerts fire when a component's calibration factor exceeds 1.5× (model is optimistic) or falls below 0.5× (model is conservative), with a minimum 10% confidence threshold to suppress noise from single events.
