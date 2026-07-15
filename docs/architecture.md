# Architecture

---

## Project structure

```
ccs-workover-forecast/
├── app.py                          # Streamlit dashboard (11 tabs)
├── requirements.txt
├── data/
│   ├── assumptions/
│   │   ├── component_failure_assumptions.csv   # MTTF + detection probability database
│   │   ├── monitoring_config.csv               # Per-tier detection_prob overrides
│   │   ├── assumption_quality.csv              # Source quality, confidence, sensitivity register
│   │   ├── cost_assumptions.csv                # Per-event costs, CO₂ uplift, post-workover verification
│   │   ├── co2_stream_quality.csv              # Contaminant tiers → injectivity / corrosion multipliers
│   │   └── scenario_config.csv
│   ├── observations/
│   │   └── observed_events.csv                 # Real field failure/degradation events for calibration
│   ├── calibration/                            # Auto-generated per-field calibration factor exports
│   └── outputs/                                # Downloaded CSVs land here
└── src/
    ├── config_loader.py            # Loads CSV assumptions
    ├── reliability_model.py        # MTTF sampling, bathtub curve, cumulative probability
    ├── failure_generator.py        # Vectorised failure + detection + preventive event generation
    ├── intervention_engine.py      # Barrier hierarchy and escalation rules
    ├── campaign_scheduler.py       # Deferred queue batching; immediate event grouping
    ├── bundling.py                 # Co-location discount logic
    ├── economics.py                # Cost aggregation and P10/P50/P90 summary
    ├── simulation.py               # Monte Carlo orchestration
    ├── field_calibration.py        # Observed vs expected rate comparison; MTTF calibration; maturity score
    ├── reporting.py                # Aggregation, health index, heatmap data, narratives
    ├── plotting.py                 # Plotly chart functions
    ├── calibration.py              # Calibration score and uncertainty decomposition
    ├── explainability.py           # Plain-language KPI traceability narratives
    └── qa.py                       # Validation metrics and sanity checks
```

---

## Simulation pipeline stages

| Stage | Source file | Key logic |
|---|---|---|
| 1 — Setup | `simulation.py` · `config_loader.py` | Scenario multipliers, monitoring override, CO₂ uplift, fleet coverage patch |
| 2 — Failure generation | `failure_generator.py` | Triangular MTTF sample per (sim, well); bathtub curve; Bernoulli draws; penetration mask |
| 3 — Intervention decisions | `intervention_engine.py` | Barrier hierarchy; per-mode flow-assurance escalation; multi-failure escalation |
| 4 — Campaign scheduling | `campaign_scheduler.py` | Immediate queue; deferred batch by size or max-age; mob cost allocation |
| 5 — Economics | `economics.py` | Per-(sim, year) cost aggregation; P10/P50/P90 lifecycle statistics |

---

## Dashboard tabs

| Tab | Contents | View modes |
|---|---|---|
| Overview | KPI cards (P50/P90 workovers, lifecycle cost, peak demand, threshold split), asset health index, KPI traceability expanders, executive narrative | All |
| Lifecycle Forecast | Annual P10/P50/P90 workover fan chart, bathtub curve with phase annotations, cost fan chart | Engineering, Developer |
| Risk & Failure Modes | 5×5 risk matrix, component lifecycle failure probability heatmap, cost contribution breakdown, risk traceability | Engineering, Developer |
| Campaign Planning | Bubble Gantt across sample simulations, deferred queue evolution, immediate vs deferred split, campaign story | Engineering, Developer |
| Economics | Waterfall cost breakdown, lifecycle cost distribution, cost by component, cost traceability | Engineering, Developer |
| Scenario Comparison | Side-by-side comparison of multiple scenario runs | Executive, Engineering, Developer |
| Field Calibration | Reliability maturity score; per-component calibration factors (observed vs expected rate); drift alerts; recommended MTTF updates; observed event log | Engineering, Reviewer, Developer |
| Model QA | Calibration score, assumption quality register, critical calibration gaps, MTTF uncertainty tornado, validation metrics, sanity checks, campaign type breakdown | Engineering, Reviewer, Developer |
| Assumptions | Live view of all CSV assumption tables with quality register and engineering defensibility panel | Engineering, Reviewer, Developer |
| Simulation Trace | Full decision audit — Bernoulli draws, detection events, campaign assignments; worst year explainability; per-event audit table | Engineering, Reviewer, Developer |
| Well Journey | Per-well event timeline, component health chart, decision path flowchart for any selected event | Engineering, Reviewer, Developer |

**View mode selector** (Executive / Engineering / Reviewer / Developer) in the sidebar controls tab visibility:

- **Executive** — Overview and Scenario Comparison. For managers and regulators.
- **Engineering** — Full analysis including risk, campaigns, well journeys, and assumptions. For well integrity and intervention engineers.
- **Reviewer** — Assumptions, calibration, QA, and full audit trail. For technical reviewers who need to challenge every model decision.
- **Developer** — All engineering content plus model internals, calibration metrics, raw distributions, and diagnostic drill-downs. For model validators and reliability engineers.

---

## Downloadable outputs

| File | Contents |
|---|---|
| `failure_event_log.csv` | Every simulated event — includes `trigger_type`, `sampled_mttf`, `lifecycle_multiplier`, `adjusted_probability` |
| `annual_forecast.csv` | Per-year P10/P50/P90 intervention and workover demand |
| `campaign_log.csv` | Every campaign with type, size, cost breakdown |
| `simulation_summary.csv` | Lifecycle P10/P50/P90 statistics for the active run |
| `annual_economics.csv` | Annual cost breakdown (intervention + mob + deferred injection) |
