"""
Simulation trace builder.

Joins the enriched failure_df with the campaign event map to produce
the full audit trail of the simulation.
"""
import numpy as np
import pandas as pd


def build_simulation_trace(
    failure_df: pd.DataFrame,
    campaign_event_map: pd.DataFrame,
    params: dict,
) -> pd.DataFrame:
    """
    Build the simulation trace dataframe for the Simulation Trace tab.

    Returns one row per intervention event, enriched with:
    - Calendar year (field life year + first injection year)
    - Field ID
    - Campaign assignment (campaign_id, campaign_type, campaign_year, campaign_size)
    - Renamed columns matching the trace specification
    """
    if failure_df.empty:
        return pd.DataFrame()

    trace = failure_df.copy()

    first_injection_year = int(params.get('first_injection_year', 2030))
    field_id = params.get('field_id') or 'Global'

    trace['year_of_field_life'] = trace['year']
    trace['calendar_year'] = first_injection_year + trace['year'] - 1
    trace['field_id'] = field_id

    # Friendly renames to match trace spec
    trace = trace.rename(columns={
        'sampled_mttf':            'effective_mttf',
        'lifecycle_multiplier':    'bathtub_multiplier',
        'adjusted_probability':    'annual_failure_probability',
        'estimated_duration_days': 'downtime_days',
        'estimated_cost':          'intervention_cost',
    })

    # can_defer: True when the event is deferrable (batched), False when immediate
    trace['can_defer'] = trace['immediate_or_deferred'] == 'deferred'

    # Join campaign assignment
    if not campaign_event_map.empty and len(campaign_event_map.columns) >= 5:
        trace = trace.merge(
            campaign_event_map.rename(columns={'fail_year': 'year_of_field_life'}),
            on=['simulation_id', 'well_id', 'year_of_field_life', 'component'],
            how='left',
        )
    else:
        trace['campaign_id']   = pd.NA
        trace['campaign_type'] = pd.NA
        trace['campaign_year'] = pd.NA
        trace['campaign_size'] = pd.NA

    # Ensure all expected trace columns exist (fill missing ones)
    for col in ['bernoulli_draw', 'cumulative_failure_probability',
                'failure_occurred', 'detected', 'detection_probability',
                'threshold_triggered', 'sampled_p10_mttf', 'sampled_p50_mttf', 'sampled_p90_mttf',
                'start_age', 'effective_year', 'seismic_event_year']:
        if col not in trace.columns:
            trace[col] = pd.NA

    # Canonical column order for the trace
    ordered_cols = [
        'simulation_id', 'field_id', 'well_id', 'well_type', 'component', 'display_name',
        'year_of_field_life', 'calendar_year', 'start_age', 'effective_year',
        'sampled_p10_mttf', 'sampled_p50_mttf', 'sampled_p90_mttf', 'effective_mttf',
        'bathtub_multiplier', 'annual_failure_probability', 'cumulative_failure_probability',
        'bernoulli_draw', 'failure_occurred', 'detected', 'detection_probability',
        'barrier_class', 'can_defer', 'threshold_triggered',
        'intervention_type', 'trigger_type', 'escalated', 'seismic_event_year',
        'campaign_id', 'campaign_type', 'campaign_year', 'campaign_size',
        'intervention_cost', 'downtime_days',
    ]
    available = [c for c in ordered_cols if c in trace.columns]
    remaining = [c for c in trace.columns if c not in ordered_cols]
    return trace[available + remaining].reset_index(drop=True)


def compute_worst_year_breakdown(
    failure_df: pd.DataFrame,
    campaign_log: pd.DataFrame,
    annual_forecast: pd.DataFrame,
    params: dict,
) -> dict:
    """
    Compute explainability breakdown for the peak demand year.
    Returns a dict with all data needed to render the worst-year panel.
    """
    if annual_forecast.empty or failure_df.empty:
        return {}

    first_injection_year = int(params.get('first_injection_year', 2030))
    operating_years = int(params.get('operating_years', 30))

    peak_row = annual_forecast.loc[annual_forecast['p50_workovers'].idxmax()]
    peak_year_field = int(peak_row['year'])
    peak_year_cal = first_injection_year + peak_year_field - 1
    field_age = peak_year_field

    # Component breakdown in peak year (averaged across simulations)
    peak_events = failure_df[failure_df['year'] == peak_year_field]
    dn_col = 'display_name' if 'display_name' in peak_events.columns else 'component'
    comp_breakdown = (
        peak_events.groupby(dn_col).size()
        .div(params.get('n_simulations', 1))
        .round(1)
        .sort_values(ascending=False)
        .to_dict()
    )

    # Campaign breakdown in peak year
    camp_year = campaign_log[campaign_log['campaign_year'] == peak_year_field] if not campaign_log.empty else pd.DataFrame()
    campaign_breakdown = {}
    if not camp_year.empty:
        campaign_breakdown = (
            camp_year.groupby('campaign_type')['simulation_id'].count()
            .div(params.get('n_simulations', 1))
            .round(1)
            .to_dict()
        )

    wear_start = max(3, int(operating_years * 0.70))
    phase = (
        'wear-out' if peak_year_field >= wear_start
        else ('infant mortality' if peak_year_field <= 2 else 'useful life')
    )

    top_comps = list(comp_breakdown.keys())[:3]
    top_comp_str = ' and '.join(str(c) for c in top_comps) if top_comps else 'multiple components'

    p50_interventions = float(peak_row.get('p50_workovers', 0))
    n_campaigns_py = sum(campaign_breakdown.values())

    narrative = (
        f"Year {peak_year_field} (calendar {peak_year_cal}) becomes the peak intervention year "
        f"because {top_comp_str} components enter the {phase} phase simultaneously. "
    )
    if n_campaigns_py > 0:
        narrative += (
            f"{n_campaigns_py:.1f} campaigns (P50) are required to execute "
            f"the resulting intervention backlog."
        )

    return {
        'peak_year_field':    peak_year_field,
        'peak_year_calendar': peak_year_cal,
        'field_age':          field_age,
        'p50_interventions':  p50_interventions,
        'phase':              phase,
        'comp_breakdown':     comp_breakdown,
        'campaign_breakdown': campaign_breakdown,
        'n_campaigns_py':     n_campaigns_py,
        'narrative':          narrative,
    }
