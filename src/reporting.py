import pandas as pd
import numpy as np


def build_annual_forecast(failure_df: pd.DataFrame, operating_years: int) -> pd.DataFrame:
    """
    Build per-year P10/P50/P90 intervention and workover demand.
    Each percentile is computed over the distribution of counts across simulations.
    Years with no events in a given simulation contribute a count of zero.
    """
    if failure_df.empty:
        return pd.DataFrame()

    all_sim_ids = failure_df['simulation_id'].unique()

    total_counts = (
        failure_df.groupby(['simulation_id', 'year']).size()
        .unstack(fill_value=0)
        .reindex(index=all_sim_ids, fill_value=0)
    )
    workover_counts = (
        failure_df[failure_df['intervention_type'] == 'full_workover']
        .groupby(['simulation_id', 'year']).size()
        .unstack(fill_value=0)
        .reindex(index=all_sim_ids, fill_value=0)
    )

    records = []
    for yr in range(1, operating_years + 1):
        tc = total_counts[yr] if yr in total_counts.columns else pd.Series(0, index=all_sim_ids)
        wc = workover_counts[yr] if yr in workover_counts.columns else pd.Series(0, index=all_sim_ids)
        records.append({
            'year': yr,
            'p10_interventions': tc.quantile(0.10),
            'p50_interventions': tc.quantile(0.50),
            'p90_interventions': tc.quantile(0.90),
            'mean_interventions': tc.mean(),
            'p10_workovers': wc.quantile(0.10),
            'p50_workovers': wc.quantile(0.50),
            'p90_workovers': wc.quantile(0.90),
            'mean_workovers': wc.mean(),
        })

    return pd.DataFrame(records)


def build_component_summary(failure_df: pd.DataFrame) -> pd.DataFrame:
    if failure_df.empty:
        return pd.DataFrame()
    return (
        failure_df.groupby(['component', 'intervention_type', 'severity'])
        .agg(
            total_events=('simulation_id', 'count'),
            total_cost=('estimated_cost', 'sum'),
            mean_cost_per_event=('estimated_cost', 'mean'),
        )
        .reset_index()
        .sort_values('total_cost', ascending=False)
    )


def get_highest_risk_component(failure_df: pd.DataFrame) -> str:
    if failure_df.empty:
        return 'N/A'
    high = failure_df[failure_df['severity'] == 'high']
    pool = high if not high.empty else failure_df
    counts = pool.groupby('component').size()
    return str(counts.idxmax()) if not counts.empty else 'N/A'


def build_scenario_comparison(scenario_results: dict) -> pd.DataFrame:
    rows = [{'scenario': k, **v} for k, v in scenario_results.items()]
    return pd.DataFrame(rows)


def format_cost(value: float) -> str:
    if value >= 1e9:
        return f'${value / 1e9:.2f}B'
    if value >= 1e6:
        return f'${value / 1e6:.1f}M'
    if value >= 1e3:
        return f'${value / 1e3:.0f}K'
    return f'${value:.0f}'


# ── Component display mapping (supports old and new component names) ──────────

def _get_display_name(comp: str, failure_df: pd.DataFrame) -> str:
    """Prefer the display_name column from failure_df if available."""
    if 'display_name' in failure_df.columns and not failure_df.empty:
        match = failure_df[failure_df['component'] == comp]['display_name']
        if not match.empty:
            return str(match.iloc[0])
    return comp.replace('_', ' ').title()


def _get_barrier_class(comp: str, failure_df: pd.DataFrame) -> str:
    if 'barrier_class' in failure_df.columns and not failure_df.empty:
        match = failure_df[failure_df['component'] == comp]['barrier_class']
        if not match.empty:
            return str(match.iloc[0])
    return 'production'


# Consequence weight by barrier class (used in health score)
_CONSEQUENCE_WEIGHT = {
    'safety':         1.0,
    'production':     0.7,
    'flow_assurance': 0.5,
    'monitoring':     0.3,
}

# Max expected annual adjusted failure probability (worst-case ceiling for health = 0)
# Derived from: at P10 MTTF × wear-out 3× multiplier
_MAX_ANNUAL_PROB = {
    'trsv':           0.10,   # 1-exp(-1/30) × 3 ≈ 0.095
    'tubing':         0.085,
    'packer':         0.13,
    'gauge':          0.18,
    'fiber_optics':   0.22,
    'wellhead':       0.065,
    'tree':           0.075,
    'cement_barrier': 0.10,
    'casing':         0.075,
    'injectivity':    0.35,
}


def compute_asset_health_scores(
    failure_df: pd.DataFrame,
    n_simulations: int,
    n_wells: int,
    operating_years: int,
) -> dict[str, dict]:
    """
    Dynamic health index per component.

    Score = 100 − weighted_failure_rate − weighted_consequence − age_penalty
    Range: 0–100. Healthy ≥ 85, Monitor 70–84, At Risk 50–69, Critical < 50.
    """
    result = {}

    components = (
        failure_df[['component', 'display_name', 'barrier_class']].drop_duplicates()
        if ('display_name' in failure_df.columns and 'barrier_class' in failure_df.columns
            and not failure_df.empty)
        else pd.DataFrame(columns=['component', 'display_name', 'barrier_class'])
    )

    if failure_df.empty:
        return {}

    total_well_years = max(n_simulations * n_wells * operating_years, 1)
    observed_rate = failure_df.groupby('component').size() / total_well_years

    for _, row in components.iterrows():
        comp = row['component']
        label = row['display_name']
        bclass = row.get('barrier_class', 'production')

        rate = observed_rate.get(comp, 0.0)
        max_rate = _MAX_ANNUAL_PROB.get(comp, 0.10)
        consequence_w = _CONSEQUENCE_WEIGHT.get(bclass, 0.7)

        # Normalised observed rate (0–1)
        rate_penalty = min(rate / max_rate, 1.0) * 50.0            # up to 50 pts

        # Consequence contribution
        consequence_penalty = consequence_w * 20.0                  # up to 20 pts

        # Age degradation factor: compare late-life vs early-life rates
        if 'year' in failure_df.columns:
            comp_df = failure_df[failure_df['component'] == comp]
            late_start = max(1, int(operating_years * 0.65))
            early_rate = comp_df[comp_df['year'] <= max(2, int(operating_years * 0.3))].shape[0]
            late_rate  = comp_df[comp_df['year'] >= late_start].shape[0]
            ratio = (late_rate / max(early_rate, 1)) / max(operating_years * 0.3, 1)
            age_penalty = min(ratio * 5.0, 30.0)                    # up to 30 pts
        else:
            age_penalty = 0.0

        score = float(max(0.0, min(100.0, 100.0 - rate_penalty - consequence_penalty - age_penalty)))

        if score >= 85:
            status = 'Healthy'
            desc = 'Operating within expected reliability envelope'
        elif score >= 70:
            status = 'Monitor'
            desc = 'Elevated failure rate — increase inspection frequency'
        elif score >= 50:
            status = 'At Risk'
            desc = 'Significant degradation — prioritise intervention planning'
        else:
            status = 'Critical'
            desc = 'High failure rate — safety case review recommended'

        result[label] = {
            'score': round(score, 1),
            'status': status,
            'description': desc,
            'barrier_class': bclass,
            'component': comp,
        }

    return result


def generate_executive_narrative(
    failure_df: pd.DataFrame,
    annual_forecast: pd.DataFrame,
    campaign_log: pd.DataFrame,
    lifecycle_summary: dict,
    params: dict,
) -> list[str]:
    lines = []
    n_wells = params.get('n_wells', 0)
    operating_years = params.get('operating_years', 30)
    n_simulations = params.get('n_simulations', 1)

    p50_wo    = lifecycle_summary.get('p50_workovers', 0)
    p90_wo    = lifecycle_summary.get('p90_workovers', 0)
    p50_cost  = lifecycle_summary.get('p50_lifecycle_cost', 0)
    p90_cost  = lifecycle_summary.get('p90_lifecycle_cost', 0)
    p50_peak  = lifecycle_summary.get('p50_peak_annual_demand', 0)
    p50_camps = lifecycle_summary.get('p50_campaigns', 0)

    # 1 — Overall demand
    lines.append(
        f"P50 forecast indicates **{p50_wo:.0f} full workovers** over {operating_years} years "
        f"across {n_wells} wells, with a peak annual intervention demand of **{p50_peak:.0f} wells/year**. "
        f"The P90 scenario reaches **{p90_wo:.0f} workovers** — representing "
        f"**{(p90_wo/max(p50_wo,1)-1)*100:.0f}% upside exposure**."
    )

    # 2 — Cost
    if p50_cost > 0:
        lines.append(
            f"P50 lifecycle intervention cost is **{format_cost(p50_cost)}** "
            f"(~{format_cost(p50_cost / max(n_wells, 1))} per well over field life). "
            f"Under P90 conditions cost rises to **{format_cost(p90_cost)}**, "
            f"a **{format_cost(p90_cost - p50_cost)} contingency** above the base estimate."
        )

    # 3 — Primary cost driver (with new display_name column)
    if not failure_df.empty:
        dn_col = 'display_name' if 'display_name' in failure_df.columns else 'component'
        comp_costs = failure_df.groupby(dn_col)['estimated_cost'].sum()
        total_cost = comp_costs.sum()
        if total_cost > 0:
            top = comp_costs.idxmax()
            pct = comp_costs[top] / total_cost * 100
            lines.append(
                f"**{top}** is the primary cost driver, contributing "
                f"**{pct:.0f}%** of total intervention expenditure. "
                f"Reliability improvements on this component will deliver the greatest lifecycle cost reduction."
            )

    # 4 — Lifecycle phase insight (wear-out acceleration)
    if not failure_df.empty and 'lifecycle_multiplier' in failure_df.columns:
        late_start = max(1, int(operating_years * 0.65))
        late_events = failure_df[failure_df['year'] >= late_start]
        early_events = failure_df[failure_df['year'] <= max(2, int(operating_years * 0.25))]
        if len(early_events) > 0:
            ratio = (len(late_events) / max(operating_years * 0.35, 1)) / \
                    (len(early_events) / max(operating_years * 0.25, 1))
            if ratio > 1.5:
                lines.append(
                    f"The wear-out phase (Year {late_start}+) produces **{ratio:.1f}× more interventions** "
                    f"per year than early-life. Late-life corrosion, elastomer degradation, and injectivity "
                    f"decline are the primary drivers — pre-position rig resources after Year {late_start - 2}."
                )

    # 5 — Preventive vs reactive split
    if not failure_df.empty and 'trigger_type' in failure_df.columns:
        prev_pct = (failure_df['trigger_type'] == 'preventive').mean() * 100
        lines.append(
            f"**{prev_pct:.0f}% of interventions are preventive** (threshold-triggered), "
            f"with the remainder reactive (failure-driven). "
            f"Increasing the intervention threshold reduces planned interventions but raises reactive risk."
        )

    # 6 — Campaign efficiency
    if not campaign_log.empty and p50_camps > 0:
        avg_size = campaign_log['n_wells'].mean()
        immediate_pct = (
            (campaign_log['campaign_type'] == 'immediate').sum() / len(campaign_log) * 100
        )
        lines.append(
            f"Campaign batching consolidates deferred interventions into an average of "
            f"**{p50_camps:.0f} campaigns** over field life ({avg_size:.1f} wells/campaign). "
            f"**{immediate_pct:.0f}%** of campaigns are emergency mobilisations triggered by "
            f"safety-critical or escalated failures."
        )

    return lines


def compute_component_contributions(failure_df: pd.DataFrame) -> pd.DataFrame:
    """Percentage contribution of each component to event count and lifecycle cost."""
    if failure_df.empty:
        return pd.DataFrame()

    dn_col = 'display_name' if 'display_name' in failure_df.columns else 'component'

    df = (
        failure_df.groupby([dn_col, 'component'])
        .agg(event_count=('simulation_id', 'count'), total_cost=('estimated_cost', 'sum'))
        .reset_index()
        .rename(columns={dn_col: 'display_name'})
    )
    total_events = df['event_count'].sum()
    total_cost   = df['total_cost'].sum()
    df['event_pct'] = df['event_count'] / max(total_events, 1) * 100
    df['cost_pct']  = df['total_cost']  / max(total_cost, 1)  * 100
    df['cost_m']    = df['total_cost'] / 1e6

    return df.sort_values('total_cost', ascending=False).reset_index(drop=True)


def compute_heatmap_data(
    component_assumptions: pd.DataFrame,
    operating_years: int,
    failure_prob_multiplier: float = 1.0,
) -> pd.DataFrame:
    """
    Compute theoretical annual adjusted failure probability for each
    (component, year) using P50 MTTF. Returns long-form DataFrame suitable
    for the lifecycle heatmap visualisation.

    Columns: component, display_name, barrier_class, year, base_prob,
             lifecycle_multiplier, adjusted_prob
    """
    from .reliability_model import mttf_to_annual_prob, lifecycle_multiplier_vector
    import numpy as np

    lc_mult = lifecycle_multiplier_vector(operating_years)
    rows = []
    for _, comp in component_assumptions.iterrows():
        P10 = float(comp['P10_MTTF'])
        P90 = float(comp['P90_MTTF'])
        mid = (P10 + P90) / 2.0
        base_prob = float(mttf_to_annual_prob(np.array([mid]))[0]) * failure_prob_multiplier
        base_prob = min(base_prob, 0.95)
        for yr_idx, lm in enumerate(lc_mult):
            adj = min(base_prob * lm, 0.95)
            rows.append({
                'component':          comp['component'],
                'display_name':       comp['display_name'],
                'barrier_class':      comp['barrier_class'],
                'year':               yr_idx + 1,
                'base_prob':          base_prob,
                'lifecycle_multiplier': lm,
                'adjusted_prob':      adj,
            })
    return pd.DataFrame(rows)
