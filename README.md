# CCS Workover Forecast

A reliability-driven Monte Carlo simulator that estimates future workover and intervention demand for CCS wells over a 20–40 year lifecycle.

Inspired by the methodology in **SPE-232388-MS** — *"Methodology for Estimating CCS Wells Workover Frequency"* — and built in Python/Streamlit.

---

## What it does

Given a population of CCS wells and their component reliability assumptions, the simulator answers:

> *How many failures and workovers will emerge over time, and what resources will be needed?*

It produces P10/P50/P90 workover demand, lifecycle cost distributions, campaign batching plans, and scenario comparisons — all traceable back to the underlying assumptions.

---

## Quickstart

```bash
# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the dashboard
streamlit run app.py
```

Then open http://localhost:8501 in your browser.

---

## Project structure

```
ccs-workover-forecast/
├── app.py                          # Streamlit dashboard (7 tabs)
├── requirements.txt
├── data/
│   ├── assumptions/
│   │   ├── component_failure_assumptions.csv   # MTTF database
│   │   ├── cost_assumptions.csv
│   │   └── scenario_config.csv
│   └── outputs/                    # Downloaded CSVs land here
└── src/
    ├── config_loader.py            # Loads CSV assumptions
    ├── reliability_model.py        # MTTF sampling, bathtub curve, cumulative probability
    ├── failure_generator.py        # Vectorised failure + preventive event generation
    ├── intervention_engine.py      # Barrier hierarchy and escalation rules
    ├── campaign_scheduler.py       # Deferred queue batching
    ├── economics.py                # Cost aggregation and P10/P50/P90 summary
    ├── simulation.py               # Monte Carlo orchestration
    ├── reporting.py                # Aggregation, health index, heatmap data, narratives
    └── plotting.py                 # Plotly chart functions
```

---

## Simulation pipeline

```
Well population
  → MTTF sampling          (triangular P10/P90 per simulation per component)
  → Bathtub curve          (infant 1.5× · useful life 1.0× · wear-out up to 3.0×)
  → Bernoulli failure trials + preventive threshold events
  → Barrier hierarchy      (safety→immediate · monitoring→deferrable · flow assurance→rigless)
  → Campaign batching      (deferred queue + size/age triggers)
  → Economics              (per-event cost + mob overhead + deferred injection penalty)
  → P10/P50/P90 outputs
  → Dashboard + CSV exports
```

---

## Configuration

All assumptions live in `data/assumptions/`. Edit the CSVs to change reliability parameters, costs, or scenarios — no code changes required.

### Component reliability database

`component_failure_assumptions.csv` — one row per component, MTTF-based.

| Field | Description |
|---|---|
| `component` | Component identifier |
| `display_name` | Human-readable label shown in the dashboard |
| `category` | Functional grouping (tubulars, barriers, monitoring, etc.) |
| `barrier_class` | `safety` / `production` / `monitoring` / `flow_assurance` |
| `P10_MTTF` | Pessimistic mean time to failure (years) — short MTTF, high failure rate |
| `P90_MTTF` | Optimistic mean time to failure (years) — long MTTF, low failure rate |
| `consequence_level` | 1 (Negligible) to 5 (Catastrophic) — drives the risk matrix position |
| `intervention_type` | `full_workover` / `light_intervention` / `rigless_intervention` |
| `can_defer` | Whether the intervention can be queued for batching |
| `safety_critical` | Forces immediate intervention regardless of batching rules |
| `default_cost` | Per-event cost used when cost assumptions don't override |
| `default_duration_days` | Typical intervention duration |
| `injector_only` | Component only present on injection wells |
| `trsv_only` | Component only enabled when TRSV/SCSSV is active (offshore config) |

Ten components are modelled across four barrier classes:

| Component | Barrier class | P10 MTTF | P90 MTTF | Intervention type |
|---|---|---|---|---|
| TRSV / SCSSV | Safety | 30 yr | 65 yr | Rigless |
| Cement Barrier | Safety | 30 yr | 70 yr | Full workover |
| Casing | Safety | 40 yr | 80 yr | Full workover |
| Tubing String | Production | 35 yr | 55 yr | Full workover |
| Injection Packer | Production | 22 yr | 38 yr | Full workover |
| Wellhead | Production | 45 yr | 75 yr | Light intervention |
| Tree | Production | 40 yr | 70 yr | Light intervention |
| Injectivity / Flow Assurance | Flow assurance | 8 yr | 20 yr | Rigless (escalates) |
| P/T Gauge | Monitoring | 15 yr | 26 yr | Rigless |
| Fiber Optics | Monitoring | 12 yr | 26 yr | Rigless |

### Reliability model

Each simulation draws an MTTF value per component from a triangular distribution between P10 and P90 (mode at midpoint). Annual failure probability is derived via the exponential reliability model:

```
P(fail) = 1 − exp(−1 / sampled_MTTF)
```

A **bathtub curve lifecycle multiplier** is applied on top of the base probability each year:

| Phase | Years | Multiplier | Failure modes |
|---|---|---|---|
| Infant mortality | 1–2 | 1.5× | Installation damage, commissioning defects, poor packer setting |
| Useful life | 3–70% of field life | 1.0× | Random, uncorrelated failures |
| Wear-out | Final 30% of field life | 1.0× → 3.0× | Corrosion, fatigue, elastomer degradation, injectivity decline |

The wear-out multiplier increases as `1 + ((year − wear_start) / (life − wear_start))² × 2`.

### Intervention probability threshold

A user-controlled threshold (70–95%, default 90%) triggers **preventive interventions** when the cumulative failure probability of a component exceeds that level. Preventive events are planned, deferrable, and priced at 80% of the reactive cost to reflect the saving from scheduling in advance.

Reducing the threshold increases planned interventions and total cost, but lowers unplanned failure risk.

### Cost assumptions

`cost_assumptions.csv` — costs by scenario (`base_case`, `offshore_high_cost`).

| Cost item | Base case |
|---|---|
| Rig mobilisation | $2,000,000 / campaign |
| Full workover | $2,500,000 / well |
| Light intervention | $500,000 / well |
| Rigless intervention | $200,000 / event |
| Deferred injection cost | $50,000 / day / well |

The deferred injection penalty applies to rig workovers that sit in the deferred queue. Cost = (days waiting) × (daily rate) × (number of deferred rig jobs), summed per well.

### Scenario configuration

`scenario_config.csv` — five built-in scenarios with failure probability multipliers and cost multipliers.

| Scenario | Failure multiplier | Cost multiplier |
|---|---|---|
| Base Case | 1.0× | 1.0× |
| Conservative Design | 0.6× | 1.1× |
| Low-Cost Design | 1.5× | 0.9× |
| High Corrosion | 1.8× | 1.0× |
| Offshore High-Cost | 1.2× | 1.6× |

---

## Dashboard tabs

| Tab | Contents |
|---|---|
| Executive Summary | KPI cards (P50/P90 workovers, lifecycle cost, peak demand, threshold split), dynamic asset health index with per-component scores, executive narrative |
| Lifecycle Forecast | Annual P10/P50/P90 workover fan chart, bathtub curve with phase annotations, cost fan chart |
| Risk & Failure Modes | 5×5 risk matrix, component lifecycle failure probability heatmap, cost contribution breakdown |
| Campaign Planning | Bubble Gantt across sample simulations, deferred queue evolution, immediate vs deferred split |
| Economics | Waterfall cost breakdown (average per simulation), lifecycle cost distribution, cost by component |
| Scenario Comparison | Add results from multiple scenario runs to compare side by side |
| Assumptions | Live view of all CSV assumption tables |

---

## Outputs (downloadable from sidebar)

| File | Contents |
|---|---|
| `failure_event_log.csv` | Every simulated failure event — includes `trigger_type`, `sampled_mttf`, `lifecycle_multiplier`, `adjusted_probability` |
| `annual_forecast.csv` | Per-year P10/P50/P90 intervention and workover demand |
| `campaign_log.csv` | Every simulated campaign with type, size, cost breakdown |
| `simulation_summary.csv` | Lifecycle P10/P50/P90 statistics for the active run |
| `annual_economics.csv` | Annual cost breakdown (intervention + mob + deferred injection) |

---

## Modelling notes

### Cost convention

- `estimated_cost` (per event) covers all per-intervention costs including materials and rig time.
- `mobilisation_cost` (per campaign) is the rig mob/demob overhead added once per campaign.
- `deferred_injection_cost` is the CO₂ storage revenue lost while a workover waits in the deferred queue, calculated as the sum of each deferred rig well's actual waiting time in days × daily rate.
- Total lifecycle cost = sum of all three. No double-counting.

### Barrier hierarchy

The intervention engine applies priority rules based on `barrier_class`:

- **Safety** (TRSV, Cement, Casing) — always immediate, never deferred.
- **Production** (Tubing, Packer, Wellhead, Tree) — batched into campaigns unless escalated.
- **Monitoring** (Gauge, Fiber Optics) — always deferrable.
- **Flow assurance** (Injectivity) — rigless intervention first; escalates to full workover on the second failure on the same well.

### Escalation rule

If a well accumulates ≥ 2 medium-or-high severity failures within any 3-year window, all remaining deferred events on that well are promoted to immediate priority.

### Campaign trigger logic

Deferred interventions accumulate in a per-simulation queue. A batch campaign fires when either:
- The queue reaches `campaign_threshold` wells (default 5), or
- The oldest queued item has waited `max_deferral_years` years (default 3).

Immediate interventions (safety-critical or escalated) are executed in the year they occur, each as a standalone mobilisation.

### Randomness and reproducibility

The global random seed (default 42) is set once in `run_simulation()`. The same inputs always produce the same results. Change the seed in `src/simulation.py` for a different draw.

---

## Relationship to SPE-232388-MS

| Paper element | Implementation |
|---|---|
| Component-level failure taxonomy | 10-component MTTF database in `component_failure_assumptions.csv` |
| MTTF uncertainty quantification | Triangular sampling between P10/P90 MTTF per simulation in `reliability_model.py` |
| Bathtub curve lifecycle model | `lifecycle_multiplier_vector()` — infant / useful life / wear-out phases |
| Injector vs monitoring well distinction | `failure_generator.py` — monitoring wells skip injector-only components |
| Stochastic workover frequency estimation | Vectorised Monte Carlo in `simulation.py` over N realisations |
| P10/P50/P90 workover demand output | `reporting.py` → `build_annual_forecast()` |
| Campaign batching concept | `campaign_scheduler.py` — deferred queue with threshold and age triggers |
| Barrier integrity hierarchy | `intervention_engine.py` — safety / production / monitoring / flow assurance classes |

---

## Known limitations

1. **No well state after repair** — a repaired component has the same MTTF as a new one. A repair-to-as-new vs repair-to-as-old distinction would improve late-life accuracy.
2. **No rig availability constraint** — the scheduler does not cap simultaneous campaigns by rig count.
3. **Single deferred injection rate** — all deferred rig workovers are penalised at the same daily rate regardless of well productivity.
4. **No spatial or cluster logic** — all wells are treated as independent.
5. **Exponential (memoryless) failure model** — Weibull shape parameter is not yet implemented; the current model does not capture increasing hazard within a phase beyond the bathtub multiplier.

## Recommended next improvements

1. Add Weibull shape parameter to capture intra-phase hazard growth (infrastructure already in `reliability_model.py`).
2. Add a rig fleet capacity constraint to cap simultaneous campaigns.
3. Add per-well repair history to track cumulative failure counts and adjust future MTTF.
4. Enable CSV upload in the Assumptions tab for project-specific calibration without file editing.
5. Add a sensitivity tornado chart showing which MTTF assumption has the largest impact on P90 lifecycle cost.
