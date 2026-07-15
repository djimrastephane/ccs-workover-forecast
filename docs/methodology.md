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

## Lifecycle shapes

Each component carries a `lifecycle_shape` that maps operating year to a hazard multiplier applied on top of the base annual failure probability.

**`bathtub`** (default — mechanical, well-age-driven):

| Phase | Years | Multiplier | Failure modes |
|---|---|---|---|
| Infant mortality | 1–2 | 1.5× | Installation damage, commissioning defects, poor packer setting |
| Useful life | 3–70% of field life | 1.0× | Random, uncorrelated failures |
| Wear-out | Final 30% of field life | 1.0× → 1.8× | Corrosion, fatigue, elastomer degradation |

Wear-out multiplier: `1 + ((year − wear_start) / (life − wear_start)) × 0.8` — a linear ramp to 1.8× maximum, reflecting gradual degradation rather than a sudden cliff at end of life.

**Injection-driven shapes** (geochemical flow-assurance sub-modes, DOE/NETL-2020/2634 Exhibit 3-1). These mechanisms start their clock at CO₂ injection, not well construction, so they ignore the `start_age` offset — a converted legacy well has the same hydrate/halite/scaling exposure as a new well:

| Shape | Used by | Profile |
|---|---|---|
| `infant` | Hydrate Control | 2.0× at startup (year 1), declining linearly to 1.0× by year 5 — hydrates form at high-P/low-T startup and shutdown transients |
| `plateau` | Halite Plugging | 0.8× → 1.2× over the first 40% of field life as near-wellbore dry-out accumulates, then holds |
| `wear_out` | Carbonate Scaling, Microbial Plugging | 1.0× useful life, then the standard ramp to 1.8× — slow geochemical/biological accumulation, no infant phase |

### Fleet age mix (`start_age`)

Converted legacy O&G wells enter the simulation mid-life rather than at Year 1. The **Fleet age mix** sidebar controls set a legacy fraction and a conversion age; that fraction of wells (chosen randomly, fixed per run) is offset on the bathtub curve:

```
effective_year = operating_year + start_age
```

A well converted at age 20 in a 30-year field skips infant mortality entirely and enters the wear-out ramp immediately (wear_start = year 21). Phase boundaries stay anchored to the field design life; effective years beyond design life hold at the 1.8× ceiling. MTTF sampling is unchanged — the offset shifts *where* on the hazard curve the well operates, not the underlying component reliability. For worst-case conversions with unknown construction history, combine the age offset with the **Legacy Well Conversion** scenario multiplier; for well-assessed, fully re-completed conversions use the age offset alone.

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
- **Flow assurance** (injectivity sub-modes) — rigless intervention first; a repeat failure of the **same** persistent formation-damage mode (halite, carbonate, microbial) on the same well escalates to full workover. Hydrate Control never escalates — hydrate events are operational transients remediated at the wellhead (methanol/glycol), and recur by design after shutdowns.

---

## CO₂ stream quality

Co-sequestered contaminants — chiefly H₂S, plus CH₄, N₂, SO₂, O₂ — act through two orthogonal multipliers set by the **CO₂ Stream Quality** sidebar tier (`co2_stream_quality.csv`):

- **Injectivity multiplier** (×1.0 / ×1.3 / ×1.8) — applies to the four flow-assurance sub-modes: contaminants occupy pore space, reduce CO₂ relative permeability, and amplify near-wellbore geochemical scaling.
- **Corrosion multiplier** (×1.0 / ×1.5 / ×2.5) — applies to casing, cement barrier, tubing, injection packer, and tubing hanger seal: H₂S forms sulphurous/carbonic acid with water, aggressively corroding carbon steel, cement, and elastomers even below 100 ppm.

Both stack multiplicatively with the scenario `failure_prob_multiplier`, keeping capture-source purity separate from reservoir-fluid aggressiveness. Stream quality is a static project input (set by the capture facility), not a dynamic failure mode. Note the **High Corrosion** scenario retains its blanket 1.8× multiplier: for a sour-stream-driven case, prefer Base Case + sour tier over High Corrosion, which now represents reservoir-fluid aggressiveness (formation brine chemistry) rather than stream purity.

---

## Induced seismicity

Induced/triggered seismicity (DOE/NETL-2020/2634 §3.1.2–3.1.3) is the model's only **field-level correlated** failure trigger: one Bernoulli draw per (simulation, year) — at the sidebar-set `annual_seismic_prob` — affects **all wells simultaneously**, unlike the per-well independent trials used everywhere else. In a seismic event year:

- **Casing** annual failure probability is multiplied (default 7×) — fault displacement can shear casing at the crossing (Exhibit 3-2, leakage pathway *e*).
- **Cement barrier** probability is multiplied (default 10×) — cement is more brittle under transient shock, cracking micro-annuli.

Failures attributed to a seismic year carry `trigger_type = 'seismic'` — a reactive subtype that follows the same urgency rules (undetected seismic safety failures go to emergency campaigns; because the event is field-correlated, several wells typically share one emergency mobilisation in that year).

**Detection — the stoplight protocol.** Seismic damage is sudden and subsurface: baseline detection is only 10%. A functioning **Seismic Monitoring Array** on the well raises it to 70% — representing the mandatory post-event inspection (40 CFR §146.89 mechanical integrity testing) locating the damage before leakage escalates, converting the response to a planned intervention (deferred, 80% cost). The array must be installed (its `penetration_rate`) and must not have itself failed that year.

Geology tiers in `seismic_config.csv`: stable (0.3%/yr, 3×/5×), reference (1.0%/yr, 7×/10×), fault-proximal (3.0%/yr, 15×/20×), plus a "not modelled" tier that disables the mechanism entirely and reproduces the pre-seismic model bit-for-bit at the same seed.

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
