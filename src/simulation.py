import numpy as np
import pandas as pd

from .config_loader import (
    load_component_assumptions,
    load_intervention_rules,
    load_cost_assumptions,
    load_scenario_config,
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
    seed: int = 42,
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
    rng = np.random.default_rng(seed)

    # ── Load assumptions ──────────────────────────────────────────────────────
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

    cost_scenario = 'offshore_high_cost' if scenario_id == 'offshore_high_cost' else 'base_case'
    raw_costs = load_cost_assumptions(cost_scenario)
    cost_assumptions = {k: v * cost_multiplier for k, v in raw_costs.items()}

    # ── Generate failures (vectorised across all simulations) ─────────────────
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
    failure_df = apply_intervention_decisions(failure_df)

    # ── Schedule campaigns ────────────────────────────────────────────────────
    campaign_log = schedule_campaigns(
        failure_df,
        cost_assumptions,
        campaign_threshold=campaign_threshold,
        max_deferral_years=max_deferral_years,
        operating_years=operating_years,
    )

    # ── Economics ─────────────────────────────────────────────────────────────
    annual_costs = compute_annual_economics(failure_df, campaign_log, operating_years)
    lifecycle_summary = compute_lifecycle_summary(annual_costs, campaign_log, failure_df)

    return failure_df, campaign_log, annual_costs, lifecycle_summary
