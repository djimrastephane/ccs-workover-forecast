"""Generates traceable KPI explanations."""
import pandas as pd
from .reporting import format_cost


def explain_cost_driver(contributions, component_assumptions, params):
    if contributions.empty:
        return []
    top = contributions.iloc[0]
    comp_name = top['display_name']
    comp_id = top['component']
    cost_pct = top['cost_pct']
    event_pct = top['event_pct']
    lines = [
        f"**{comp_name}** contributes **{cost_pct:.0f}%** of lifecycle intervention cost "
        f"({event_pct:.0f}% of events)."
    ]
    comp_row = component_assumptions[component_assumptions['component'] == comp_id]
    if not comp_row.empty:
        row = comp_row.iloc[0]
        p10, p90 = row['P10_MTTF'], row['P90_MTTF']
        int_type = row['intervention_type']
        barrier = row['barrier_class']
        lines.append(
            f"MTTF range: **{p10:.0f}–{p90:.0f} years** (P10–P90 uncertainty band). "
            f"Intervention type: **{int_type.replace('_', ' ')}**. "
            f"Barrier class: **{barrier}**."
        )
        if barrier == 'safety':
            lines.append(
                "As a **safety barrier**, all failures trigger immediate mobilisation without batching "
                "— each event incurs a standalone rig mob cost."
            )
        elif barrier == 'production':
            lines.append(
                "As a **production barrier**, failures are batched into deferred campaigns, "
                "but escalate to immediate if ≥2 high-severity failures accumulate within 3 years."
            )
    if params.get('scenario_id') == 'offshore_high_cost':
        lines.append(
            "The **Offshore High-Cost** scenario applies a **1.6× cost multiplier**, "
            "amplifying mobilisation costs disproportionately."
        )
    lines.append(
        "Reliability improvements on this component (e.g. selective inhibition, improved seal materials, "
        "or increased inspection frequency) will deliver the largest lifecycle cost reduction."
    )
    return lines


def explain_peak_demand(annual_forecast, failure_df, params):
    if annual_forecast.empty:
        return []
    operating_years = params.get('operating_years', 30)
    wear_start = max(3, int(operating_years * 0.70))
    peak_row = annual_forecast.loc[annual_forecast['p50_workovers'].idxmax()]
    peak_year = int(peak_row['year'])
    peak_demand = peak_row['p50_workovers']
    lines = [
        f"Peak workover demand of **{peak_demand:.1f}/year** (P50) occurs in **Year {peak_year}**."
    ]
    if peak_year >= wear_start:
        lines.append(
            f"Year {peak_year} is in the **wear-out phase** (begins Year {wear_start} "
            f"= {int(operating_years*0.7)}% of field life). The bathtub curve applies an increasing "
            f"multiplier up to **3.0×** at end of life, representing accelerating corrosion, fatigue, "
            f"and injectivity decline."
        )
    elif peak_year <= 2:
        lines.append(
            f"Peak in Year {peak_year} reflects the **infant mortality phase** (Years 1–2, "
            f"multiplier 1.5×), where installation damage, commissioning defects, and packer setting "
            f"failures dominate."
        )
    if not failure_df.empty:
        dn_col = 'display_name' if 'display_name' in failure_df.columns else 'component'
        peak_comps = (
            failure_df[failure_df['year'] == peak_year]
            .groupby(dn_col).size()
            .sort_values(ascending=False)
            .head(3)
        )
        if not peak_comps.empty:
            comp_str = ', '.join([f"**{c}**" for c in peak_comps.index])
            lines.append(
                f"Dominant components at peak: {comp_str}. "
                f"Pre-position rig resources in Year {max(1, peak_year-2)}."
            )
    return lines


def explain_campaign_count(campaign_log, lifecycle_summary, params):
    if campaign_log.empty:
        return []
    campaign_threshold = params.get('campaign_threshold', 5)
    max_deferral_years = params.get('max_deferral_years', 3)
    thr_pct = params.get('intervention_threshold', 0.90) * 100
    p50_camps = lifecycle_summary.get('p50_campaigns', 0)
    avg_size = campaign_log['n_wells'].mean()
    imm_n = campaign_log[campaign_log['campaign_type'].isin(['immediate', 'emergency'])].shape[0]
    imm_pct = imm_n / max(len(campaign_log), 1) * 100
    lines = [
        f"P50 of **{p50_camps:.0f} campaigns** over field life, averaging **{avg_size:.1f} wells/campaign**."
    ]
    drivers = []
    if imm_pct > 40:
        drivers.append(
            f"**{imm_pct:.0f}% are immediate/emergency** — safety failures bypass the deferred queue "
            f"and trigger standalone mobilisations"
        )
    if campaign_threshold <= 4:
        drivers.append(
            f"low campaign threshold (**{campaign_threshold} wells**) triggers batching quickly, "
            f"generating many small campaigns"
        )
    if thr_pct <= 80:
        drivers.append(
            f"low intervention threshold (**{thr_pct:.0f}%**) generates many preventive events, "
            f"filling the deferred queue faster"
        )
    if max_deferral_years <= 2:
        drivers.append(
            f"short max deferral (**{max_deferral_years} years**) forces frequent queue flushes "
            f"even below threshold size"
        )
    if drivers:
        lines.append("Campaign count is driven by: " + "; ".join(drivers) + ".")
    lines.append(
        "To reduce campaigns without increasing risk: raise campaign threshold, extend max deferral, "
        "or increase the intervention probability threshold."
    )
    return lines


def explain_highest_risk(highest_risk, contributions, component_assumptions, failure_df):
    if not highest_risk or highest_risk == 'N/A':
        return []
    label = highest_risk.replace('_', ' ').title()
    lines = [f"**{label}** has the highest count of high-severity failure events."]
    comp_row = component_assumptions[component_assumptions['component'] == highest_risk]
    if not comp_row.empty:
        row = comp_row.iloc[0]
        p10, p90 = row['P10_MTTF'], row['P90_MTTF']
        barrier = row['barrier_class']
        consequence = row.get('consequence_level', '?')
        lines.append(
            f"MTTF range: **{p10:.0f}–{p90:.0f} years** (P10–P90). "
            f"Barrier class: **{barrier}**. "
            f"Consequence level: **{consequence}/5** (1=Negligible, 5=Catastrophic)."
        )
        if barrier in ('production', 'safety'):
            lines.append(
                "Rig-based intervention required — this drives the highest per-event cost "
                "and the longest supply chain lead time."
            )
    if not failure_df.empty:
        n_affected = failure_df[failure_df['component'] == highest_risk]['well_id'].nunique()
        lines.append(
            f"This component is present in **{n_affected} wells** in the simulation — "
            f"maximum portfolio exposure."
        )
    return lines
