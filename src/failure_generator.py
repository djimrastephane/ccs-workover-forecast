"""
Failure generator — vectorised Monte Carlo failure event production.

Model:
  1. Sample MTTF per (simulation, component) from triangular(P10, mid, P90)
  2. Convert to base annual probability via exponential reliability model
  3. Apply scenario multiplier
  4. Apply lifecycle (bathtub-curve) multiplier per year
  5. Bernoulli trial: failure = random < adjusted_probability
  6. Add threshold-based preventive events (planned interventions before
     cumulative failure probability exceeds the user-set threshold)
"""
import numpy as np
import pandas as pd

from .reliability_model import (
    sample_mttf,
    mttf_to_annual_prob,
    lifecycle_multiplier_vector,
    cumulative_failure_probability,
    threshold_year as compute_threshold_year,
)

# Components only applicable to injector wells
_INJECTOR_ONLY = {'injectivity'}
# Components only applicable when TRSV is enabled (offshore / safety config)
_TRSV_ONLY = {'trsv'}

_SEVERITY_MAP = {5: 'high', 4: 'high', 3: 'medium', 2: 'low', 1: 'low'}

_FAILURE_MODES = {
    'trsv':            'valve_failure',
    'tubing':          'corrosion_leak',
    'packer':          'seal_failure',
    'gauge':           'sensor_failure',
    'fiber_optics':    'signal_loss',
    'wellhead':        'valve_failure',
    'tree':            'seal_degradation',
    'cement_barrier':  'micro_annulus',
    'casing':          'integrity_loss',
    'injectivity':     'scale_plugging',
}

# Barrier class → immediate_or_deferred default
_BARRIER_PRIORITY = {
    'safety':         'immediate',
    'production':     'deferred',
    'monitoring':     'deferred',
    'flow_assurance': 'deferred',
}

_OUTPUT_COLUMNS = [
    'simulation_id', 'year', 'well_id', 'well_type', 'component', 'display_name',
    'barrier_class', 'failure_mode', 'severity', 'trigger_type',
    'sampled_mttf', 'base_probability', 'lifecycle_multiplier', 'adjusted_probability',
    'intervention_required', 'intervention_type', 'immediate_or_deferred',
    'estimated_duration_days', 'estimated_cost', 'injection_impact',
]


def _get_event_cost(intervention_type: str, comp_row, cost_assumptions: dict) -> float:
    """Cost lookup: try cost_assumptions dict first, fall back to component default."""
    mapping = {
        'full_workover':        'full_workover_cost',
        'light_intervention':   'light_intervention_cost',
        'rigless_intervention': 'rigless_intervention_cost',
    }
    key = mapping.get(intervention_type)
    if key and key in cost_assumptions:
        return float(cost_assumptions[key])
    return float(comp_row.get('default_cost', 0))


def generate_all_failures(
    n_simulations: int,
    n_injectors: int,
    n_monitoring: int,
    operating_years: int,
    component_assumptions: pd.DataFrame,
    intervention_rules: pd.DataFrame,        # kept for API compat, not used
    cost_assumptions: dict,
    failure_prob_multiplier: float,
    scssv_enabled: bool,
    rng: np.random.Generator,
    intervention_threshold: float = 0.90,
) -> pd.DataFrame:
    """
    Generate all failure events across n_simulations, n_wells, n_years.

    Returns DataFrame with one row per (simulation, well, component, year) event.
    Events include both reactive failures (Bernoulli trials) and preventive
    interventions triggered when cumulative failure probability exceeds the threshold.
    """
    n_wells = n_injectors + n_monitoring
    well_ids = np.array(
        [f'INJ_{i+1:03d}' for i in range(n_injectors)]
        + [f'MON_{i+1:03d}' for i in range(n_monitoring)]
    )
    well_types = np.array(['injector'] * n_injectors + ['monitoring'] * n_monitoring)
    is_monitoring = well_types == 'monitoring'
    is_injector   = ~is_monitoring

    lc_mult = lifecycle_multiplier_vector(operating_years)  # shape (n_years,)

    frames = []

    for _, comp in component_assumptions.iterrows():
        comp_name = comp['component']

        # Applicability gates
        if comp_name in _TRSV_ONLY and not scssv_enabled:
            continue

        P10 = float(comp['P10_MTTF'])
        P90 = float(comp['P90_MTTF'])
        consequence = int(comp['consequence_level'])
        severity = _SEVERITY_MAP.get(consequence, 'medium')
        intervention_type = str(comp['intervention_type'])
        barrier_class = str(comp['barrier_class'])
        can_defer = bool(comp['can_defer'])
        safety_critical = bool(comp['safety_critical'])
        default_imm = _BARRIER_PRIORITY.get(barrier_class, 'deferred')
        imm_or_def = 'immediate' if safety_critical or not can_defer else default_imm
        duration = float(comp['default_duration_days'])
        cost = _get_event_cost(intervention_type, comp, cost_assumptions)
        has_injection_impact = severity in ('high', 'medium')
        display_name = str(comp['display_name'])
        failure_mode = _FAILURE_MODES.get(comp_name, comp_name)
        injector_only = bool(comp.get('injector_only', False))

        # ── Sample MTTF per simulation ────────────────────────────────────────
        mttf = sample_mttf(P10, P90, rng, n_simulations)          # (n_sims,)
        base_prob = mttf_to_annual_prob(mttf)                      # (n_sims,)
        base_prob = np.minimum(base_prob * failure_prob_multiplier, 0.95)

        # ── Adjusted probability matrix (n_sims, n_years) ────────────────────
        adj_prob = np.minimum(
            base_prob[:, np.newaxis] * lc_mult[np.newaxis, :],
            0.95,
        )

        # ── Reactive failures — Bernoulli trials ──────────────────────────────
        draws = rng.random((n_simulations, n_wells, operating_years))
        failures = draws < adj_prob[:, np.newaxis, :]  # (n_sims, n_wells, n_years)

        if injector_only:
            failures[:, is_monitoring, :] = False

        sim_idx, well_idx, year_idx = np.where(failures)

        if len(sim_idx) > 0:
            frames.append(pd.DataFrame({
                'simulation_id':       sim_idx + 1,
                'year':                year_idx + 1,
                'well_id':             well_ids[well_idx],
                'well_type':           well_types[well_idx],
                'component':           comp_name,
                'display_name':        display_name,
                'barrier_class':       barrier_class,
                'failure_mode':        failure_mode,
                'severity':            severity,
                'trigger_type':        'reactive',
                'sampled_mttf':        mttf[sim_idx],
                'base_probability':    base_prob[sim_idx],
                'lifecycle_multiplier': lc_mult[year_idx],
                'adjusted_probability': adj_prob[sim_idx, year_idx],
                'intervention_required': True,
                'intervention_type':   intervention_type,
                'immediate_or_deferred': imm_or_def,
                'estimated_duration_days': duration,
                'estimated_cost':      cost,
                'injection_impact':    has_injection_impact,
            }))

        # ── Preventive events — threshold-based ───────────────────────────────
        cum_fp = cumulative_failure_probability(adj_prob)  # (n_sims, n_years)
        prev_years = compute_threshold_year(cum_fp, intervention_threshold)
        # shape (n_sims,); value = 1-based year, or n_years+1 if never reached

        # Only generate events where threshold is reached within lifecycle
        eligible_sims = np.where(prev_years <= operating_years)[0]

        if len(eligible_sims) > 0:
            p_years = prev_years[eligible_sims]  # 1-based preventive year

            # Which wells are applicable?
            if injector_only:
                applicable_wells = np.where(is_injector)[0]
            else:
                applicable_wells = np.arange(n_wells)

            n_ew = len(applicable_wells)
            # Build event rows: one per (eligible_sim, applicable_well)
            sim_rep  = np.repeat(eligible_sims, n_ew)
            yr_rep   = np.repeat(p_years, n_ew)
            well_rep = np.tile(applicable_wells, len(eligible_sims))

            frames.append(pd.DataFrame({
                'simulation_id':       sim_rep + 1,
                'year':                yr_rep,
                'well_id':             well_ids[well_rep],
                'well_type':           well_types[well_rep],
                'component':           comp_name,
                'display_name':        display_name,
                'barrier_class':       barrier_class,
                'failure_mode':        failure_mode,
                'severity':            severity,
                'trigger_type':        'preventive',
                'sampled_mttf':        mttf[sim_rep],
                'base_probability':    base_prob[sim_rep],
                'lifecycle_multiplier': lc_mult[yr_rep - 1],
                'adjusted_probability': adj_prob[sim_rep, yr_rep - 1],
                'intervention_required': True,
                'intervention_type':   intervention_type,
                'immediate_or_deferred': 'deferred',   # preventive = planned
                'estimated_duration_days': duration,
                'estimated_cost':      cost * 0.80,    # 20% saving for planned
                'injection_impact':    has_injection_impact,
            }))

    if not frames:
        return pd.DataFrame(columns=_OUTPUT_COLUMNS)

    df = pd.concat(frames, ignore_index=True)

    # Deduplicate: if a well has BOTH a reactive failure AND a preventive event
    # in the same year for the same component, keep only the reactive one.
    has_both = df.duplicated(
        subset=['simulation_id', 'well_id', 'component', 'year'], keep=False
    )
    if has_both.any():
        # Within duplicates, prefer reactive
        dup_df = df[has_both].copy()
        dup_df['_rank'] = (dup_df['trigger_type'] == 'reactive').astype(int)
        keep_idx = dup_df.groupby(
            ['simulation_id', 'well_id', 'component', 'year']
        )['_rank'].idxmax()
        non_dup_idx = df.index[~has_both]
        df = df.loc[non_dup_idx.union(keep_idx)].reset_index(drop=True)

    return df
