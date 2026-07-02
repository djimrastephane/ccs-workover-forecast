# Cost Modelling

---

## Cost assumptions

> **These figures are illustrative North Sea analogues and must be replaced with project-specific costs before using outputs for any commercial or investment decision.** Rig day-rates, workover costs, and deferred injection penalties vary significantly by geography, water depth, rig type, and operator contract. Edit `data/assumptions/cost_assumptions.csv` to reflect your project.

`cost_assumptions.csv` — costs by scenario (`base_case`, `offshore_high_cost`).

| Cost item | Base case (illustrative) | Notes |
|---|---|---|
| Rig mobilisation | $2,000,000 / campaign | North Sea analogue — replace with project rig spread rate |
| Full workover | $2,500,000 / well | Before CO₂ uplift — covers tubing pull, re-completion |
| Light intervention | $500,000 / well | Before CO₂ uplift — wellhead / tree work, no tubing pull |
| Rigless intervention | $200,000 / event | Before CO₂ uplift — wireline or coiled tubing only |
| Deferred injection cost | $50,000 / day / well | Carbon credit proxy — high uncertainty, do not use for investment decisions |
| Post-workover verification | $200,000 / full workover | CBL + casing inspection + pressure test |
| CO₂ handling uplift factor | 1.15× | Applied to all per-event intervention costs |

---

## CO₂ handling uplift

1.15× base (1.20× offshore): covers CO₂-rated BOP equipment and special procedures — per NZTC/DNV CCS Wells Technology Roadmap §4.2.1. Applied multiplicatively to rigless, light, and full workover costs before the scenario cost multiplier.

---

## Co-location bundling discount

Default 25%: when multiple components fail on the same well in the same simulation year, the most expensive component pays the full standalone cost; each additional component pays `discount_factor × standalone_cost`. Reflects shared rig mobilisation, shared BOP rigging, and parallel workover efficiency. The discount applies only to `estimated_cost` — it does not affect workover or event counts. Configurable via sidebar slider (0–60%).

---

## Post-workover verification

Mandatory CBL + casing inspection + pressure test required before CO₂ re-injection clearance after any full rig workover. Added as a fixed adder on top of the full workover cost (after CO₂ uplift).

---

## Cost convention

- `estimated_cost` (per event) covers all per-intervention costs including materials and rig time.
- `mobilisation_cost` (per campaign) is the rig mob/demob overhead added once per campaign.
- `deferred_injection_cost` is the CO₂ storage revenue lost while a workover waits in the deferred queue.
- Planned interventions (preventive or threshold-triggered) are priced at 80% of the equivalent reactive cost.
- Total lifecycle cost = sum of all three. No double-counting.

---

## Deferred injection penalty

Applies to rig workovers sitting in the deferred queue. Cost = (days waiting) × (daily rate) × (deferred rig jobs), summed per well.
