# CCS Workover Forecast

[![CI](https://github.com/djimrastephane/ccs-workover-forecast/actions/workflows/ci.yml/badge.svg)](https://github.com/djimrastephane/ccs-workover-forecast/actions/workflows/ci.yml)

A Monte Carlo simulator for forecasting intervention demand across a CCS well fleet over a 20–40 year storage lifecycle. Built in Python/Streamlit.

> Developed after reading SPE-232388-MS, which raised the question of how to quantify CCS well intervention demand under uncertainty over a multi-decade storage operation.

---

## Problem

CCS operators face a planning problem with no good analogue in conventional oil and gas:

- **No CCS-specific reliability database exists.** As of 2026, the global CO₂ injection fleet numbers fewer than 50 commercial wells. No CCS equivalent of OREDA has been published. All available failure rate data comes from hydrocarbon-service analogues.
- **Storage operations span 20–40 years.** Integrity decisions made today will affect wells for decades, through phases (infant mortality, useful life, wear-out) with very different failure behaviour.
- **Uncertainty is structural, not resolvable by more analysis.** The range between P10 and P90 workover demand is not model error — it is the honest representation of what we do not yet know about how CO₂ wells age.

This tool does not eliminate that uncertainty. It makes it legible and plannable.

---

## What this tool does

This tool answers four questions:

1. **How many interventions are likely?** — P10/P50/P90 workover demand over the full storage lifecycle.
2. **When will they occur?** — Annual fan charts showing when demand peaks and what drives it.
3. **Will they cluster into campaigns?** — Campaign batching logic that reflects real operational response: emergency mobilisations, deferred batches, co-location savings.
4. **How sensitive are the estimates to uncertainty?** — Sensitivity tornado, scenario comparison, and a field calibration engine that progressively replaces literature assumptions with observed field data.

The application estimates operational consequences arising from uncertainty in component reliability assumptions. It does not predict the exact failure of a particular well.

---

## Demo

[![Demo](docs/screenshot_portfolio.png)](https://github.com/djimrastephane/ccs-workover-forecast/raw/main/docs/demo.mp4)

---

## Screenshots

**Lifecycle Forecast** — P10/P50/P90 annual workover demand fan chart with bathtub curve and cost profile.

![Lifecycle Forecast](docs/screenshot_portfolio.png)

**Well Journey** — Single-well operational history: component health evolution, intervention timeline, and cost breakdown for one stochastic scenario.

![Well Journey](docs/screenshot_well_journey.png)

---

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Then open http://localhost:8501 in your browser.

---

## Simulation pipeline

```mermaid
%%{init: {'theme': 'dark'}}%%
flowchart TD
    classDef inputNode  fill:#1e3a5f,stroke:#3b82f6,stroke-width:2px,color:#bfdbfe
    classDef settings   fill:#1e3a5f,stroke:#60a5fa,stroke-width:2px,color:#bfdbfe,rx:20
    classDef stage1     fill:#134e4a,stroke:#14b8a6,stroke-width:2px,color:#ccfbf1
    classDef stage2     fill:#431407,stroke:#f97316,stroke-width:2px,color:#fed7aa
    classDef stage3     fill:#422006,stroke:#f59e0b,stroke-width:2px,color:#fde68a
    classDef stage4     fill:#3b0764,stroke:#a855f7,stroke-width:2px,color:#e9d5ff
    classDef stage5     fill:#14532d,stroke:#22c55e,stroke-width:2px,color:#bbf7d0
    classDef outputNode fill:#1e1b4b,stroke:#818cf8,stroke-width:1px,color:#c7d2fe
    classDef appNode    fill:#27272a,stroke:#e2e8f0,stroke-width:2px,color:#f4f4f5

    subgraph INPUTS["📥  What goes in"]
        F1["📊 Equipment reliability data\nComponent MTTF · monitoring detection rates\nFleet coverage — which wells have each component"]
        F2["🔍 Monitoring programme\nMinimal · Standard · Comprehensive\nControls how often problems are caught before escalation"]
        F3["💰 Cost data\nRig day-rates · repair cost by intervention type\nCO₂ handling premium · post-workover inspection"]
        F4["⚙️ Scenario\nRisk environment: base case, high corrosion, legacy wells\nScales both failure likelihood and repair costs"]
        UP(["🎛️ Simulation settings\nWells · operating life · Monte Carlo runs\nFleet coverage — fibre optics, flowmeters, CIV, etc."])
    end

    S1["🔧 Stage 1 — Setup\nLoad scenario multipliers and base cost data\nSet detection capability per monitoring level\nApply fleet coverage mask — uninstalled\ncomponents cannot fail or incur cost"]

    S2["⚡ Stage 2 — Failure generation\nRun Monte Carlo scenarios in parallel\nEach well draws its own random failure timeline\nBathtub curve: higher risk early and near end-of-life\nEarly detection → planned repair, not emergency"]

    S3["🚦 Stage 3 — Intervention decisions\nSafety-critical failures → immediate emergency response\nFlow or monitoring failures → deferred repair queue\nRepeat failure on same well → escalate to full workover\nTwo serious failures within 3 years → well treated as critical"]

    S4["🏗️ Stage 4 — Campaign scheduling\nEmergency repairs → mobilise rig in the same year\nDeferred repairs → batch once enough wells accumulate\nor before the oldest queued item waits too long\nRig mobilisation cost shared across all campaign wells"]

    S5["📈 Stage 5 — Cost aggregation\nSum repair + mobilisation + lost-injection costs\nper well, per year, across all scenarios\nReport P10 · P50 · P90 of the full distribution"]

    subgraph OUTPUTS["📤  What comes out"]
        O1["📋 Failure event log\nEvery failure · every well · every scenario"]
        O2["📅 Campaign schedule\nTiming, size and cost of each workover campaign"]
        O3["💹 Annual cost profile\nYear-by-year spend distribution"]
        O4["📊 Lifecycle summary\nP10 · P50 · P90 total cost and peak demand"]
        O5["🗺️ Campaign event map\nLinks each failure event to its campaign ID"]
    end

    APP["🖥️ Dashboard\nWorkover fan charts · risk matrix · campaign Gantt\nLifecycle economics · asset health · model QA\nAll results downloadable as CSV"]

    INPUTS --> S1 --> S2 --> S3 --> S4 --> S5
    S3 -.->|failure events| O1
    S4 -.->|campaign log| O2
    S4 -.->|event→campaign map| O5
    S5 -.->|annual costs| O3
    S5 -.->|lifecycle summary| O4
    O1 & O2 & O3 & O4 & O5 --> APP

    class F1,F2,F3,F4 inputNode
    class UP settings
    class S1 stage1
    class S2 stage2
    class S3 stage3
    class S4 stage4
    class S5 stage5
    class O1,O2,O3,O4,O5 outputNode
    class APP appNode
```

---

## Key capabilities

| Capability | Description |
|---|---|
| Monte Carlo uncertainty | P10/P50/P90 workover demand across up to 10,000 simulation runs |
| Bathtub curve lifecycle | Infant mortality, useful life, and wear-out phases modelled explicitly |
| 15 well components | Across 4 barrier classes: safety, production, monitoring, flow assurance |
| Barrier hierarchy | Safety failures are always immediate; production and monitoring events are deferrable |
| Campaign batching | Deferred interventions batched by fleet size or maximum wait time |
| Scenario comparison | 6 built-in scenarios: base case, high corrosion, legacy well conversion, and others |
| Field calibration | Observed field events progressively replace literature MTTF assumptions |
| Explainability | Every KPI is traceable to the underlying simulation assumptions |
| Model QA | Calibration score, sensitivity tornado, sanity checks, and assumption quality register |
| Well Journey | Full per-well operational timeline for any stochastic scenario |

---

## Documentation

| Document | Purpose |
|---|---|
| [methodology.md](docs/methodology.md) | Reliability model, bathtub curve, failure detection, intervention engine, campaign logic |
| [assumptions.md](docs/assumptions.md) | Component MTTF database, barrier classes, scenario multipliers, monitoring configuration |
| [calibration.md](docs/calibration.md) | Field calibration equations, confidence weighting, drift alerts, maturity score |
| [economics.md](docs/economics.md) | Cost assumptions, CO₂ uplift, bundling discount, deferred injection penalty |
| [validation.md](docs/validation.md) | QA metrics, sanity checks, calibration score, model challenge guide |
| [architecture.md](docs/architecture.md) | Module structure, dashboard tabs, downloadable outputs, data flow |
| [limitations.md](docs/limitations.md) | Known gaps, data maturity notice, recommended improvements |
| [references.md](docs/references.md) | Full bibliography: SPE, ISO, DNV, IEAGHG, OREDA, WellMaster |

---

## Known limitations (summary)

- All MTTF values are hydrocarbon-service analogues — no CCS-specific reliability database exists as of 2026.
- Calibration score ~38/100 (Pre-FEED): outputs are order-of-magnitude planning estimates, not engineering commitments.
- No Weibull shape parameter within lifecycle phases (exponential model only).
- No rig fleet availability constraint.
- Joule-Thomson cooling and cyclic fatigue degradation are absorbed into MTTF conservatism, not modelled mechanistically.

See [limitations.md](docs/limitations.md) for the full list and roadmap.

---

## References

Key references: SPE-232388-MS (direct methodological basis), NZTC/DNV CCS Wells Technology Roadmap 2025, PMC10407664 (JPN-1 case study), IEAGHG 2018-08, Hardiman et al. 2023 (Peloton WellMaster), ISO 16530-1, ISO 27914, DNV-RP-J203.

See [references.md](docs/references.md) for the full bibliography with annotations.
