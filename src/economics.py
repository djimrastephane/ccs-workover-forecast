import pandas as pd
import numpy as np


def compute_annual_economics(
    failure_df: pd.DataFrame,
    campaign_log: pd.DataFrame,
    operating_years: int,
) -> pd.DataFrame:
    """
    Compute annual cost breakdown across all simulations.

    Cost convention:
    - intervention_cost: per-event cost (covers materials, services, rig time)
    - mobilisation_cost: campaign-level mob/demob overhead
    - deferred_injection_cost: lost CO2 injection revenue during deferral
    Total cost = sum of all three (no double-counting).
    """
    # Per-event intervention costs by (simulation_id, year)
    if not failure_df.empty:
        int_costs = (
            failure_df.groupby(['simulation_id', 'year'])['estimated_cost']
            .sum()
            .reset_index()
            .rename(columns={'estimated_cost': 'intervention_cost'})
        )
    else:
        int_costs = pd.DataFrame(columns=['simulation_id', 'year', 'intervention_cost'])

    # Campaign overhead by (simulation_id, campaign_year)
    if not campaign_log.empty:
        overhead = (
            campaign_log.groupby(['simulation_id', 'campaign_year'])
            .agg(
                mobilisation_cost=('mobilisation_cost', 'sum'),
                deferred_injection_cost=('deferred_injection_cost', 'sum'),
            )
            .reset_index()
            .rename(columns={'campaign_year': 'year'})
        )
    else:
        overhead = pd.DataFrame(
            columns=['simulation_id', 'year', 'mobilisation_cost', 'deferred_injection_cost']
        )

    annual = (
        int_costs.merge(overhead, on=['simulation_id', 'year'], how='outer')
        .fillna(0.0)
    )
    annual['total_cost'] = (
        annual['intervention_cost']
        + annual['mobilisation_cost']
        + annual['deferred_injection_cost']
    )

    return annual


def compute_lifecycle_summary(
    annual_costs: pd.DataFrame,
    campaign_log: pd.DataFrame,
    failure_df: pd.DataFrame,
) -> dict:
    """
    Compute P10/P50/P90 lifecycle statistics across all simulations.
    """
    summary = {}

    if annual_costs.empty:
        return summary

    # Lifecycle cost per simulation
    lifecycle = annual_costs.groupby('simulation_id')['total_cost'].sum()
    for pct, label in [(0.10, 'p10'), (0.50, 'p50'), (0.90, 'p90')]:
        summary[f'{label}_lifecycle_cost'] = lifecycle.quantile(pct)
    summary['mean_lifecycle_cost'] = lifecycle.mean()

    if not failure_df.empty:
        # Full workover counts
        workovers = (
            failure_df[failure_df['intervention_type'] == 'full_workover']
            .groupby('simulation_id').size()
        )
        all_interventions = failure_df.groupby('simulation_id').size()

        for pct, label in [(0.10, 'p10'), (0.50, 'p50'), (0.90, 'p90')]:
            summary[f'{label}_workovers'] = workovers.quantile(pct) if len(workovers) else 0
            summary[f'{label}_total_interventions'] = (
                all_interventions.quantile(pct) if len(all_interventions) else 0
            )

        # Peak annual demand
        annual_demand = failure_df.groupby(['simulation_id', 'year']).size()
        peak_demand = annual_demand.groupby('simulation_id').max()
        for pct, label in [(0.50, 'p50'), (0.90, 'p90')]:
            summary[f'{label}_peak_annual_demand'] = (
                peak_demand.quantile(pct) if len(peak_demand) else 0
            )

    if not campaign_log.empty:
        campaigns_per_sim = campaign_log.groupby('simulation_id').size()
        for pct, label in [(0.50, 'p50'), (0.90, 'p90')]:
            summary[f'{label}_campaigns'] = campaigns_per_sim.quantile(pct)

    return summary
