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
| `lifecycle_shape` | Hazard-vs-time profile: `bathtub` (default, well-age-driven, offset by `start_age`), or one of the CO₂-injection-driven shapes `infant` / `plateau` / `wear_out` used by the geochemical injectivity sub-modes (see [methodology.md](methodology.md)) |
| `display_group` | Optional grouping label — the four injectivity sub-modes share `Injectivity / Flow Assurance` |

---

## Component MTTF database

Twenty components modelled across four barrier classes, covering the taxonomy in the NZTC/DNV CCS Wells Technology Roadmap (2025). Flow assurance is split into four geochemical sub-modes per DOE/NETL-2020/2634 Exhibit 3-1:

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
| Injectivity · Hydrate Control | Flow assurance | 2 yr | 8 yr | Rigless ($80k methanol/glycol) | 75% | injector_only; `infant` shape — startup/shutdown driven, recurs after interruptions; never escalates to workover |
| Injectivity · Halite Plugging | Flow assurance | 5 yr | 15 yr | Rigless ($120k water wash, escalates) | 65% | injector_only; `plateau` shape; Sleipner/AquiStore field evidence |
| Injectivity · Carbonate Scaling | Flow assurance | 10 yr | 25 yr | Rigless ($250k acid job, escalates) | 55% | injector_only; `wear_out` shape; site-dependent — set penetration_rate < 1.0 for sandstone-dominated sites |
| Injectivity · Microbial Plugging | Flow assurance | 15 yr | 35 yr | Rigless ($180k antimicrobial, escalates) | 40% | injector_only; `wear_out` shape; lowest-confidence MTTF (DOE qualitative only) |
| P/T Gauge | Monitoring | 15 yr | 26 yr | Rigless | 90% | |
| Fiber Optics | Monitoring | 12 yr | 26 yr | Full workover | 85% | conventional permanent installation strapped to tubing; replacement requires pulling the tubing string |
| CO₂ Injection Flow Meter | Monitoring | 8 yr | 22 yr | Rigless | 70% | injector_only; MMV compliance |
| Annular Pressure Monitor | Monitoring | 10 yr | 25 yr | Rigless | 85% | SCP/APB surveillance; boosts cement/casing detection while functioning |
| Seismic Monitoring Array | Monitoring | 12 yr | 30 yr | Rigless | 95% | Geophone/DAS array; raises seismic-triggered casing/cement detection 10% → 70% while functioning (stoplight protocol) |

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

## CO₂ stream quality

`co2_stream_quality.csv` — contaminant tiers for the injected CO₂ stream (DOE/NETL-2020/2634 §3.1.1 Exhibit 3-1). A static per-project input set by the capture source, orthogonal to the scenario multiplier (which represents reservoir-fluid aggressiveness).

| Tier | H₂S | Injectivity multiplier | Corrosion multiplier |
|---|---|---|---|
| Pipeline grade | < 10 ppm | 1.0× | 1.0× |
| Industrial grade | 10–200 ppm | 1.3× | 1.5× |
| Raw / sour gas stream | > 200 ppm | 1.8× | 2.5× |

The injectivity multiplier applies to the four flow-assurance sub-modes (pore-space competition, relative-permeability loss, amplified scaling). The corrosion multiplier applies to casing, cement barrier, tubing, injection packer, and tubing hanger seal (sulphurous/carbonic acid attack on carbon steel, cement, and elastomers).

---

## Induced seismicity

`seismic_config.csv` — geology tiers for the field-level seismic trigger (DOE/NETL-2020/2634 §3.1.3). The annual probability can be overridden in the sidebar with site-specific hazard data.

| Tier | Annual event probability | Casing multiplier | Cement multiplier |
|---|---|---|---|
| Not modelled | 0%/yr | — | — |
| Stable geology | 0.3%/yr | 3× | 5× |
| Reference case | 1.0%/yr | 7× | 10× |
| Fault proximity | 3.0%/yr | 15× | 20× |

Seismic-triggered failure detection is 10% without a functioning Seismic Monitoring Array and 70% with one. All seismic parameters are expert judgement flagged low-confidence in `assumption_quality.csv` — no quantitative fragility curves exist for CCS wellbores.

---

## Monitoring programme configuration

`monitoring_config.csv` — per-tier detection probability overrides applied to every component.

| Programme | Technology | Typical detection range |
|---|---|---|
| Minimal | Downhole P/T gauges + periodic wireline surveys | 10–75% |
| Standard (default) | Gauges + annulus pressure monitoring + CBL/caliper surveys | 25–90% |
| Comprehensive | DTS/DAS fibre + wireless B-annulus + corrosion monitoring | 50–92% |

See [methodology.md](methodology.md) for how detection probabilities interact with the intervention engine.
