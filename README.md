# CCS Workover Forecast

A reliability-driven Monte Carlo simulator that estimates future workover and intervention demand for CCS wells over a 20–40 year lifecycle.

Inspired by the methodology in **SPE-232388-MS** — *"Methodology for Estimating CCS Wells Workover Frequency"* — and built in Python/Streamlit.

---

## What it does

Given a population of CCS wells and their component failure assumptions, the simulator answers:

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
├── app.py                          # Streamlit dashboard (6 tabs)
├── requirements.txt
├── data/
│   ├── assumptions/
│   │   ├── component_failure_assumptions.csv
│   │   ├── intervention_rules.csv
│   │   ├── cost_assumptions.csv
│   │   └── scenario_config.csv
│   └── outputs/                    # Downloaded CSVs land here
└── src/
    ├── config_loader.py            # Loads CSV assumptions
    ├── reliability_model.py        # Annual failure probability functions
    ├── failure_generator.py        # Vectorised failure event generation
    ├── intervention_engine.py      # Escalation decision rules
    ├── campaign_scheduler.py       # Deferred queue batching
    ├── economics.py                # Cost aggregation and P10/P50/P90 summary
    ├── simulation.py               # Monte Carlo orchestration
    ├── reporting.py                # Aggregation, tables, format helpers
    └── plotting.py                 # Plotly chart functions
```

---

## Simulation pipeline

```
Well population
  → Failure generation        (vectorised: all sims × wells × components × years)
  → Intervention decisions    (escalation: ≥2 failures within 3 yr → immediate)
  → Campaign batching         (deferred queue + threshold/age triggers)
  → Economics                 (per-event cost + mob overhead + deferred injection penalty)
  → P10/P50/P90 outputs
  → Dashboard + CSV exports
```

---

## Configuration

All assumptions live in `data/assumptions/`. Edit the CSVs to change failure rates, costs, or scenarios — no code changes required.

### Component failure assumptions

`component_failure_assumptions.csv` — one row per component.

| Field | Description |
|---|---|
| `component` | Component name (tubing, packer, casing, etc.) |
| `annual_prob_base` | Base annual failure probability |
| `earliest_failure_year` | Earliest year in which this failure mode can occur |
| `severity` | `low` / `medium` / `high` |
| `immediate_action` | Whether the failure demands immediate intervention |
| `rig_based` | Whether a rig workover is required |

Components modelled:

- Tubing (corrosion/leak)
- Packer (seal failure)
- Casing (integrity loss)
- Cement barrier (micro-annulus)
- Wellhead / tree (valve failure)
- Downhole gauge (sensor failure)
- SCSSV (valve malfunction — offshore only)
- Injectivity impairment (scale/plugging — injectors only)

### Intervention rules

`intervention_rules.csv` — maps each failure mode to an intervention type, priority, and typical duration.

Intervention types: `full_workover`, `light_intervention`, `rigless_intervention`, `monitor_only`.

### Cost assumptions

`cost_assumptions.csv` — costs by scenario (`base_case`, `offshore_high_cost`).

| Cost item | Base case |
|---|---|
| Rig mobilisation | $2,000,000 / campaign |
| Full workover | $2,500,000 / well |
| Light intervention | $500,000 / well |
| Rigless intervention | $200,000 / event |
| Deferred injection cost | $50,000 / day / well |

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
| Executive Summary | Key metrics — P50/P90 workovers, lifecycle cost, peak annual demand, highest risk component |
| Lifecycle Forecast | Annual P10/P50/P90 workover and intervention demand; cumulative workovers; cost distribution |
| Failure Modes | Failures by component, intervention type split, severity distribution, cost by component |
| Campaign Planning | Campaign timeline, size distribution, deferred queue, immediate vs deferred split |
| Scenario Comparison | Add results from multiple runs to compare scenarios side by side |
| Assumptions | Live view of all four CSV assumption tables |

---

## Outputs (downloadable from sidebar)

| File | Contents |
|---|---|
| `failure_event_log.csv` | Every simulated failure event with well, component, year, cost |
| `annual_forecast.csv` | Per-year P10/P50/P90 intervention and workover demand |
| `campaign_log.csv` | Every simulated campaign with type, size, cost breakdown |
| `simulation_summary.csv` | Lifecycle P10/P50/P90 statistics for the active run |
| `annual_economics.csv` | Annual cost breakdown (intervention + mob + deferred injection) |

---

## Modelling notes

### Cost convention

- `estimated_cost` (per event) covers all per-intervention costs including materials and rig time.
- `mobilisation_cost` (per campaign) is the rig mob/demob overhead added once per campaign.
- `deferred_injection_cost` is the CO₂ storage revenue lost while a workover waits in the deferred queue.
- Total lifecycle cost = sum of all three. No double-counting.

### Escalation rule

If a well accumulates ≥ 2 medium-or-high severity failures within any 3-year window, all remaining deferred events on that well are promoted to immediate priority. The threshold and window are hardcoded in `intervention_engine.py` and can be made configurable in a future iteration.

### Campaign trigger logic

Deferred interventions accumulate in a per-simulation queue. A batch campaign fires when either:
- The queue reaches `campaign_threshold` wells (default 5), or
- The oldest queued item has waited `max_deferral_years` years (default 3).

Immediate interventions (high-severity or safety-critical) are executed in the year they occur, each as a standalone mobilisation.

### Randomness and reproducibility

The global random seed (default 42) is set once in `run_simulation()`. The same inputs will always produce the same results. Change the seed in `src/simulation.py` if you want a different draw.

---

## Relationship to SPE-232388-MS

| Paper element | Implementation |
|---|---|
| Component-level failure taxonomy | `component_failure_assumptions.csv` — tubing, packer, cement, wellhead, SCSSV, gauge |
| Injector vs monitoring well distinction | `failure_generator.py` — monitoring wells skip injector-only components |
| Stochastic workover frequency estimation | Monte Carlo loop in `simulation.py` over N realisations |
| P10/P50/P90 workover demand output | `reporting.py` → `build_annual_forecast()` |
| Campaign batching concept | `campaign_scheduler.py` — deferred queue with threshold and age triggers |

---

## Known limitations (MVP)

1. **Constant failure rates** — annual probability is time-invariant. Weibull time-dependency (increasing hazard with age) is the natural next step; `reliability_model.py` has a stub for it.
2. **No well state after repair** — a repaired component has the same failure rate as a new one. A repair-to-as-new vs repair-to-as-old distinction would improve accuracy.
3. **No rig availability constraint** — the scheduler does not cap simultaneous campaigns by rig count. A capacity constraint module would be needed for resource planning.
4. **Single deferred injection rate** — all deferred rig workovers are penalised at the same daily rate regardless of well productivity.
5. **No spatial or cluster logic** — all wells are treated as independent. Grouping geographically clustered wells into campaigns is not yet modelled.

## Recommended next improvements

1. Add Weibull hazard functions for age-dependent failure rates (plumbing already in `reliability_model.py`).
2. Add a rig fleet capacity constraint to cap simultaneous campaigns.
3. Add per-well repair history to track cumulative failure counts and adjust future rates.
4. Enable CSV upload in the Assumptions tab so users can swap in project-specific failure data without editing files.
5. Add a sensitivity tornado chart showing which failure assumption has the largest impact on P90 cost.
