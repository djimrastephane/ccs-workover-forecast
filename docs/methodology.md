# Methodology

Simulation logic for the CCS Workover Forecast tool.

---

## Reliability model

Each simulation draws an MTTF value **independently per (simulation, well)** from a triangular distribution between P10 and P90 (mode at midpoint). Drawing per well rather than per simulation prevents the artefact where all wells in a simulation age in lockstep and fail in the same year.

Annual failure probability is derived via the exponential reliability model:

```
P(fail) = 1 − exp(−1 / sampled_MTTF)
```

---

## Bathtub curve

A lifecycle multiplier is applied on top of the base annual failure probability each year:

| Phase | Years | Multiplier | Failure modes |
|---|---|---|---|
| Infant mortality | 1–2 | 1.5× | Installation damage, commissioning defects, poor packer setting |
| Useful life | 3–70% of field life | 1.0× | Random, uncorrelated failures |
| Wear-out | Final 30% of field life | 1.0× → 1.8× | Corrosion, fatigue, elastomer degradation, injectivity decline |

Wear-out multiplier: `1 + ((year − wear_start) / (life − wear_start)) × 0.8` — a linear ramp to 1.8× maximum, reflecting gradual degradation rather than a sudden cliff at end of life.

---

## Detection, monitoring programme, and trigger types

Each component has a `detection_prob` — the probability that a developing failure is identified before it escalates to an unplanned event. Detected failures are reclassified as `preventive` (planned, deferrable, 80% of reactive cost). Undetected failures remain `reactive`.

The **monitoring programme** selector (Minimal / Standard / Comprehensive) overrides `detection_prob` for every component from `monitoring_config.csv`:

| Programme | Technology | Typical detection range |
|---|---|---|
| Minimal | Downhole P/T gauges + periodic wireline surveys | 10–75% |
| Standard (default) | Gauges + annulus pressure monitoring + CBL/caliper surveys | 25–90% |
| Comprehensive | DTS/DAS fibre + wireless B-annulus + corrosion monitoring | 50–92% |

Full-scale simulations (100 wells) show ~$87M P50 lifecycle cost difference between minimal and comprehensive monitoring, confirming early-detection investment is economic.

> **Monitoring tool sensitivity floor**: the PMC10407664 JPN-1 case study found that commercial acoustic/CBL tools failed to detect a micro-annulus entirely — leakage was only identified via temperature anomalies. This is reflected in the comprehensive-tier `cement_barrier` and `casing` `detection_prob` being capped at 0.45 rather than 0.50 initially assumed. Even the best available tooling cannot guarantee detection of sub-threshold leakage rates.

A second preventive mechanism fires when **cumulative failure probability** (the product of all annual survivals to date) exceeds the user-set threshold (default 90%). This is the probability of surviving to year *t*, not the single-year probability. A threshold-preventive event is always deferrable and costs 80% of the reactive equivalent.

---

## Intervention probability threshold

A user-controlled threshold (70–95%, default 90%) triggers planned interventions before cumulative failure probability crosses that level. Reducing the threshold increases planned cost but reduces unplanned emergency campaigns.

---

## Barrier hierarchy

The intervention engine applies priority rules based on `barrier_class` and `trigger_type`:

- **Safety reactive** (undetected TRSV, Cement, Casing failures) — always immediate emergency campaign.
- **Safety preventive** (caught by inspection or monitoring) — deferrable; treated as planned maintenance.
- **Production** (Tubing, Packer, Wellhead, Tree) — deferrable; batched into campaigns unless escalated.
- **Monitoring** (Gauge, Fiber Optics) — always deferrable regardless of trigger type.
- **Flow assurance** (Injectivity) — rigless intervention first; escalates to full workover on the second failure per well.

---

## Escalation rule

If a well accumulates ≥ 2 medium-or-high severity **reactive** failures within any 3-year window, its remaining reactive deferred events are promoted to immediate priority. Preventive events are never escalated — they are already scheduled optimally.

---

## Campaign batching logic

Deferred interventions accumulate in a per-simulation queue. A batch campaign fires when either:

- The queue reaches `campaign_threshold` events (default 5), or
- The oldest queued item has waited `max_deferral_years` years (default 3).

Immediate interventions within the same year are grouped rather than executed as individual mobilisations:

- Emergency events (reactive safety failures): one shared emergency campaign per year.
- Urgent events (escalated production failures): one shared urgent campaign per year.

---

## Randomness and reproducibility

The global random seed (default 42) is set once in `run_simulation()`. The same inputs always produce the same outputs. Change the seed in `src/simulation.py` for an independent draw.

---

## P10 / P50 / P90 interpretation

The model runs the same field hundreds or thousands of times, each with a different random sequence of failures. P50 is the median outcome — half of simulated futures cost less, half cost more. P10 is the optimistic end (only 10% of futures are cheaper). P90 is the high-cost end (only 10% of futures are more expensive). The gap between P10 and P90 is the uncertainty range, driven mainly by how uncertain the reliability assumptions are.
