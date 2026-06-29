import numpy as np
import pandas as pd

from .config_loader import (
    load_component_assumptions,
    load_intervention_rules,
    load_cost_assumptions,
    load_scenario_config,
    load_monitoring_config,
)
from .failure_generator import generate_all_failures
from .intervention_engine import apply_intervention_decisions
from .campaign_scheduler import schedule_campaigns
from .economics import compute_annual_economics, compute_lifecycle_summary


def run_simulation(
    n_simulations: int = 1000,
    n_injectors: int = 80,
    n_monitoring: int = 20,
    operating_years: int = 30,
    scenario_id: str = 'base_case',
    campaign_threshold: int = 5,
    max_deferral_years: int = 3,
    intervention_threshold: float = 0.90,
    monitoring_program: str = 'standard',
    seed: int = 42,
    on_progress=None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    """
    Orchestrate the full Monte Carlo simulation pipeline.

    Flow:
        Well population
        -> vectorised failure generation (all sims at once)
        -> intervention escalation decisions
        -> campaign batching
        -> economics
        -> summary statistics

    Returns: (failure_df, campaign_log, annual_costs, lifecycle_summary)
    """
    def _progress(msg: str, frac: float):
        if on_progress is not None:
            on_progress(msg, frac)

    rng = np.random.default_rng(seed)

    # ── Load assumptions ──────────────────────────────────────────────────────
    _progress('Loading assumptions…', 0.02)
    component_assumptions = load_component_assumptions()
    intervention_rules = load_intervention_rules()
    scenario_cfg = load_scenario_config()

    if scenario_id in scenario_cfg.index:
        scen = scenario_cfg.loc[scenario_id]
        failure_prob_multiplier = float(scen['failure_prob_multiplier'])
        cost_multiplier = float(scen['cost_multiplier'])
        scssv_enabled = bool(scen['scssv_enabled'])
        # Scenario can override campaign settings if user hasn't changed them
        campaign_threshold = int(scen.get('campaign_threshold', campaign_threshold))
        max_deferral_years = int(scen.get('max_deferral_years', max_deferral_years))
    else:
        failure_prob_multiplier = 1.0
        cost_multiplier = 1.0
        scssv_enabled = True

    # ── Apply monitoring program → override detection_prob per component ──────
    monitoring_cfg = load_monitoring_config()
    if not monitoring_cfg.empty and monitoring_program in monitoring_cfg.columns:
        mon_map = dict(zip(monitoring_cfg['component'], monitoring_cfg[monitoring_program]))
        component_assumptions = component_assumptions.copy()
        component_assumptions['detection_prob'] = (
            component_assumptions['component'].map(mon_map)
            .fillna(component_assumptions['detection_prob'])
        )

    # ── Build cost assumptions with CO₂ uplift and post-workover verification ─
    cost_scenario = 'offshore_high_cost' if scenario_id == 'offshore_high_cost' else 'base_case'
    raw_costs = load_cost_assumptions(cost_scenario)

    # Extract scalars before applying cost_multiplier
    co2_uplift   = float(raw_costs.get('co2_handling_uplift_factor', 1.0))
    post_verify  = float(raw_costs.get('post_workover_verification_cost', 0.0))
    _scalar_keys = {'co2_handling_uplift_factor', 'post_workover_verification_cost'}

    cost_assumptions = {k: v * cost_multiplier for k, v in raw_costs.items()
                        if k not in _scalar_keys}

    # Apply CO₂ handling uplift to all per-event intervention costs
    for _key in ('rigless_intervention_cost', 'light_intervention_cost', 'full_workover_cost'):
        if _key in cost_assumptions:
            cost_assumptions[_key] *= co2_uplift

    # Post-workover verification: scale by both multipliers then pass to failure generator
    cost_assumptions['post_workover_verification_cost'] = post_verify * co2_uplift * cost_multiplier

    # ── Generate failures (vectorised across all simulations) ─────────────────
    _progress(f'Generating failure events across {n_simulations:,} simulations…', 0.10)
    failure_df = generate_all_failures(
        n_simulations=n_simulations,
        n_injectors=n_injectors,
        n_monitoring=n_monitoring,
        operating_years=operating_years,
        component_assumptions=component_assumptions,
        intervention_rules=intervention_rules,
        cost_assumptions=cost_assumptions,
        failure_prob_multiplier=failure_prob_multiplier,
        scssv_enabled=scssv_enabled,
        rng=rng,
        intervention_threshold=intervention_threshold,
    )

    if failure_df.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), {}

    # ── Apply intervention decision rules ─────────────────────────────────────
    _progress('Applying barrier hierarchy and escalation rules…', 0.75)
    failure_df = apply_intervention_decisions(failure_df)

    # ── Schedule campaigns ────────────────────────────────────────────────────
    _progress('Scheduling campaigns…', 0.85)
    campaign_log = schedule_campaigns(
        failure_df,
        cost_assumptions,
        campaign_threshold=campaign_threshold,
        max_deferral_years=max_deferral_years,
        operating_years=operating_years,
    )

    # ── Economics ─────────────────────────────────────────────────────────────
    _progress('Computing lifecycle economics…', 0.93)
    annual_costs = compute_annual_economics(failure_df, campaign_log, operating_years)
    lifecycle_summary = compute_lifecycle_summary(annual_costs, campaign_log, failure_df)

    _progress('Done.', 1.0)
    return failure_df, campaign_log, annual_costs, lifecycle_summary
