# Engineering Assumptions

All assumptions live in `data/assumptions/`. Edit the CSVs to change reliability parameters, costs, or scenarios — no code changes required.

---

## Component reliability database

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
| `safety_critical` | Forces reactive failures to immediate regardless of batching rules |
| `default_cost` | Per-event cost used when cost assumptions don't override |
| `default_duration_days` | Typical intervention duration |
| `injector_only` | Component only present on injection wells |
| `trsv_only` | Component only enabled when TRSV/SCSSV is active (offshore config) |
| `detection_prob` | Probability a developing failure is caught before becoming a reactive emergency |
| `penetration_rate` | Fraction of wells in the fleet that have this component installed (0.0–1.0). Default `1.0` means every well is equipped. Set to e.g. `0.6` to model a mixed fleet where only 60% of wells have this component. The equipped subset is drawn randomly from the fleet and held fixed across all simulations within a run. |

---

## Component MTTF database

Fifteen components modelled across four barrier classes, covering the taxonomy in the NZTC/DNV CCS Wells Technology Roadmap (2025):

| Component | Barrier class | P10 MTTF | P90 MTTF | Intervention type | Detection prob (standard tier) | Notes |
|---|---|---|---|---|---|---|
| TRSV / SCSSV | Safety | 30 yr | 65 yr | Rigless | 70% | trsv_only; assumes wireline-retrievable (WRTRSV) design; SPE-232388-MS Table 1 |
| Cement Barrier | Safety | 50 yr | 70 yr | Full workover | 25% | Michigan 70yr field evidence (IEAGHG 2018-08) is the longest available empirical upper bound |
| Casing | Safety | 60 yr | 150 yr | Full workover | 30% | |
| Surface Safety Valve | Safety | 15 yr | 40 yr | Rigless | 80% | |
| Casing Isolation Valve | Safety | 20 yr | 55 yr | Light | 55% | CCS-specific barrier |
| Tubing Hanger Seal | Safety | 30 yr | 70 yr | Full workover | 50% | primary metal-to-metal seal failure requires pulling tubing |
| Tubing String | Production | 35 yr | 55 yr | Full workover | 40% | |
| Injection Packer | Production | 22 yr | 38 yr | Full workover | 35% | SPE-232388-MS Table 1 |
| Wellhead | Production | 45 yr | 75 yr | Light | 60% | |
| Tree | Production | 40 yr | 70 yr | Light | 55% | |
| Hydraulic Control Line | Safety | 10 yr | 25 yr | Full workover | 85% | trsv_only; line runs outside tubing string — replacement requires pulling tubing |
| Injectivity / Flow Assurance | Flow assurance | 8 yr | 20 yr | Rigless (escalates) | 50% | injector_only |
| P/T Gauge | Monitoring | 15 yr | 26 yr | Rigless | 90% | |
| Fiber Optics | Monitoring | 12 yr | 26 yr | Full workover | 85% | conventional permanent installation strapped to tubing; replacement requires pulling the tubing string |
| CO₂ Injection Flow Meter | Monitoring | 8 yr | 22 yr | Rigless | 70% | injector_only; MMV compliance |

Safety barriers (TRSV, Cement, Casing, SSV, CIV, Tubing Hanger) carry longer MTTF values reflecting their role as the last line of defence — failures are rare, high-consequence events, not routine cost drivers. Detection probability is low for downhole safety barriers because defects (micro-annuli, casing corrosion) develop below the surface and are hard to identify without integrity testing programmes.

---

## Scenario multipliers

`scenario_config.csv` — six built-in scenarios with failure probability and cost multipliers.

| Scenario | Failure multiplier | Cost multiplier | Notes |
|---|---|---|---|
| Base Case | 1.0× | 1.0× | Balanced baseline |
| Conservative Design | 0.6× | 1.1× | High-spec wells, premium materials |
| Low-Cost Design | 1.5× | 0.9× | Cost-optimised, higher failure risk |
| High Corrosion | 1.8× | 1.3× | Aggressive CO₂ corrosion; higher intervention complexity |
| Offshore High-Cost | 1.2× | 1.6× | Deepwater or harsh environment |
| Legacy Well Conversion | 2.5× | 1.4× | Converted abandoned O&G wellbore — material incompatibility, unknown construction history; SCSSV disabled; per PMC10407664 |

---

## Monitoring programme configuration

`monitoring_config.csv` — per-tier detection probability overrides applied to every component.

| Programme | Technology | Typical detection range |
|---|---|---|
| Minimal | Downhole P/T gauges + periodic wireline surveys | 10–75% |
| Standard (default) | Gauges + annulus pressure monitoring + CBL/caliper surveys | 25–90% |
| Comprehensive | DTS/DAS fibre + wireless B-annulus + corrosion monitoring | 50–92% |

See [methodology.md](methodology.md) for how detection probabilities interact with the intervention engine.
