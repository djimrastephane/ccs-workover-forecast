"""
Failure generator — vectorised Monte Carlo failure event production.

Model:
  1. Sample MTTF per (simulation, well, component) from triangular(P10, mid, P90)
     Each well draws its own MTTF, so failures scatter naturally across years
     rather than all wells in a simulation failing in sync.
  2. Convert to base annual probability via exponential reliability model
  3. Apply scenario multiplier
  4. Apply lifecycle (bathtub-curve) multiplier per year
  5. Bernoulli trial: failure = random < adjusted_probability
  6. Detection probability: detected reactive failures become planned preventive
     events (deferred, 80% cost) rather than reactive emergencies
  7. Add threshold-based preventive events (planned interventions before
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

_INJECTOR_ONLY = {'injectivity'}
_TRSV_ONLY = {'trsv', 'control_line'}

_SEVERITY_MAP = {5: 'high', 4: 'high', 3: 'medium', 2: 'low', 1: 'low'}

_FAILURE_MODES = {
    'trsv':                    'valve_failure',
    'tubing':                  'corrosion_leak',
    'packer':                  'seal_failure',
    'gauge':                   'sensor_failure',
    'fiber_optics':            'signal_loss',
    'wellhead':                'valve_failure',
    'tree':                    'seal_degradation',
    'cement_barrier':          'micro_annulus',
    'casing':                  'integrity_loss',
    'injectivity':             'scale_plugging',
    'ssv':                     'valve_failure',
    'casing_valve':            'seal_failure',
    'control_line':            'hydraulic_leak',
    'tubing_hanger':           'seal_failure',
    'injection_flowmeter':     'sensor_failure',
    'annular_pressure_monitor': 'signal_loss',
}

# Annular Pressure Monitor (APM / SCP) boosts detection of cement and casing
# failures when functioning. Values are the effective detection probability
# WITH the APM active; the conditional re-roll is computed per-event using
# the actual baseline detection_probability already applied.
# Ref: DOE/NETL-2020/2634 §3.1.2; UIC Class VI 40 CFR §146.89
_APM_SENSITIVE = {'cement_barrier', 'casing'}
_APM_BOOST     = {'cement_barrier': 0.60, 'casing': 0.50}

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
    'sampled_p10_mttf', 'sampled_p50_mttf', 'sampled_p90_mttf',
    'cumulative_failure_probability', 'bernoulli_draw',
    'failure_occurred', 'detected', 'detection_probability', 'threshold_triggered',
    'start_age', 'effective_year',
]


def _get_event_cost(intervention_type: str, comp_row, cost_assumptions: dict) -> float:
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
    intervention_rules: pd.DataFrame,
    cost_assumptions: dict,
    failure_prob_multiplier: float,
    scssv_enabled: bool,
    rng: np.random.Generator,
    intervention_threshold: float = 0.90,
    legacy_well_fraction: float = 0.0,
    legacy_start_age: int = 15,
) -> pd.DataFrame:
    """
    Generate all failure events across n_simulations, n_wells, n_years.

    MTTF is sampled independently per (simulation, well) so that wells within
    the same simulation have different failure rates. This prevents the
    synchronised-failure artefact where all wells in a simulation reach their
    preventive-intervention threshold in exactly the same year.

    legacy_well_fraction of the fleet (chosen randomly, fixed for the whole
    run) enters the simulation at legacy_start_age years on the bathtub curve
    — modelling converted legacy wells in a mixed-age fleet. The remaining
    wells start at age 0 (current behaviour).
    """
    n_wells = n_injectors + n_monitoring
    well_ids = np.array(
        [f'INJ_{i+1:03d}' for i in range(n_injectors)]
        + [f'MON_{i+1:03d}' for i in range(n_monitoring)]
    )
    well_types = np.array(['injector'] * n_injectors + ['monitoring'] * n_monitoring)
    is_monitoring = well_types == 'monitoring'
    is_injector   = ~is_monitoring

    # Per-well start age: legacy wells are offset on the bathtub curve.
    # The rng draw happens only when a legacy fraction is requested, so an
    # all-new fleet reproduces pre-start_age results bit-for-bit at same seed.
    start_ages = np.zeros(n_wells, dtype=int)
    n_legacy = int(round(np.clip(legacy_well_fraction, 0.0, 1.0) * n_wells))
    if n_legacy > 0 and legacy_start_age > 0:
        legacy_idx = rng.permutation(n_wells)[:n_legacy]
        start_ages[legacy_idx] = int(legacy_start_age)

    # (n_wells, n_years) lifecycle matrix — one bathtub vector per start age
    _lc_by_age = {
        age: lifecycle_multiplier_vector(operating_years, start_age=age)
        for age in np.unique(start_ages)
    }
    lc_mult = np.stack([_lc_by_age[a] for a in start_ages])  # (n_wells, n_years)

    frames = []

    for _, comp in component_assumptions.iterrows():
        comp_name = comp['component']

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
        detection_prob = float(comp.get('detection_prob', 0.0))
        penetration_rate = float(comp.get('penetration_rate', 1.0))
        default_imm = _BARRIER_PRIORITY.get(barrier_class, 'deferred')
        imm_or_def = 'immediate' if safety_critical or not can_defer else default_imm
        duration = float(comp['default_duration_days'])
        cost = _get_event_cost(intervention_type, comp, cost_assumptions)
        # Post-workover integrity verification is mandatory before CO₂ re-injection
        if intervention_type == 'full_workover':
            cost += float(cost_assumptions.get('post_workover_verification_cost', 0.0))
        has_injection_impact = severity in ('high', 'medium')
        display_name = str(comp['display_name'])
        failure_mode = _FAILURE_MODES.get(comp_name, comp_name)
        injector_only = bool(comp.get('injector_only', False))

        # -- Sample MTTF per (simulation, well) --------------------------------
        # Each well gets its own draw so failures scatter across years rather
        # than all wells in a simulation ageing in lockstep.
        mttf = sample_mttf(
            P10, P90, rng, n_simulations * n_wells
        ).reshape(n_simulations, n_wells)                       # (n_sims, n_wells)

        base_prob = mttf_to_annual_prob(mttf)                   # (n_sims, n_wells)
        base_prob = np.minimum(base_prob * failure_prob_multiplier, 0.95)

        # -- Adjusted probability (n_sims, n_wells, n_years) ------------------
        adj_prob = np.minimum(
            base_prob[:, :, np.newaxis] * lc_mult[np.newaxis, :, :],
            0.95,
        )

        # -- Compute cumulative failure probability once (used for trace and threshold) --
        cum_fp_3d = cumulative_failure_probability(
            adj_prob.reshape(n_simulations * n_wells, operating_years)
        ).reshape(n_simulations, n_wells, operating_years)     # (n_sims, n_wells, n_years)

        # -- Reactive failures -- Bernoulli trials ----------------------------
        draws = rng.random((n_simulations, n_wells, operating_years))
        failures = draws < adj_prob                             # (n_sims, n_wells, n_years)

        if injector_only:
            failures[:, is_monitoring, :] = False

        # Penetration rate: which wells actually have this component installed.
        # Fixed randomly per component for the whole run (seeded by rng);
        # set penetration_rate < 1.0 in the CSV to model partial fleet coverage.
        if penetration_rate < 1.0:
            n_equipped = max(1, round(penetration_rate * n_wells))
            not_equipped = rng.permutation(n_wells)[n_equipped:]
            failures[:, not_equipped, :] = False
        else:
            not_equipped = np.empty(0, dtype=int)

        sim_idx, well_idx, year_idx = np.where(failures)

        if len(sim_idx) > 0:
            n_ev = len(sim_idx)
            ev_cost = np.full(n_ev, cost)
            ev_trigger = np.full(n_ev, 'reactive', dtype=object)
            ev_imm = np.full(n_ev, imm_or_def, dtype=object)

            # Detection: some reactive failures are caught by monitoring /
            # inspection before escalating. Detected → planned, deferred, 80% cost.
            detected_arr = np.zeros(n_ev, dtype=bool)
            if detection_prob > 0:
                detected_arr = rng.random(n_ev) < detection_prob
                ev_trigger[detected_arr] = 'preventive'
                ev_imm[detected_arr] = 'deferred'
                ev_cost[detected_arr] *= 0.80

            frames.append(pd.DataFrame({
                'simulation_id':         sim_idx + 1,
                'year':                  year_idx + 1,
                'well_id':               well_ids[well_idx],
                'well_type':             well_types[well_idx],
                'component':             comp_name,
                'display_name':          display_name,
                'barrier_class':         barrier_class,
                'failure_mode':          failure_mode,
                'severity':              severity,
                'trigger_type':          ev_trigger,
                'sampled_mttf':          mttf[sim_idx, well_idx],
                'base_probability':      base_prob[sim_idx, well_idx],
                'lifecycle_multiplier':  lc_mult[well_idx, year_idx],
                'adjusted_probability':  adj_prob[sim_idx, well_idx, year_idx],
                'intervention_required': True,
                'intervention_type':     intervention_type,
                'immediate_or_deferred': ev_imm,
                'estimated_duration_days': duration,
                'estimated_cost':        ev_cost,
                'injection_impact':      has_injection_impact,
                'sampled_p10_mttf':                P10,
                'sampled_p50_mttf':                (P10 + P90) / 2.0,
                'sampled_p90_mttf':                P90,
                'cumulative_failure_probability':  cum_fp_3d[sim_idx, well_idx, year_idx],
                'bernoulli_draw':                  draws[sim_idx, well_idx, year_idx],
                'failure_occurred':                True,
                'detected':                        detected_arr,
                'detection_probability':           detection_prob,
                'threshold_triggered':             False,
                'start_age':                       start_ages[well_idx],
                'effective_year':                  year_idx + 1 + start_ages[well_idx],
            }))

        # -- Preventive events -- threshold-based (per well) ------------------
        # Use already-computed cum_fp_3d for threshold calculation.
        prev_years = compute_threshold_year(
            cum_fp_3d.reshape(n_simulations * n_wells, operating_years),
            intervention_threshold,
        ).reshape(n_simulations, n_wells)                      # (n_sims, n_wells)

        # Injector-only: monitoring wells are ineligible for threshold events
        if injector_only:
            prev_years[:, is_monitoring] = operating_years + 1

        # Penetration rate: non-equipped wells never trigger threshold events
        if len(not_equipped) > 0:
            prev_years[:, not_equipped] = operating_years + 1

        eligible_mask = prev_years <= operating_years          # (n_sims, n_wells)
        sim_rep, well_rep = np.where(eligible_mask)
        if len(sim_rep) > 0:
            yr_rep = prev_years[sim_rep, well_rep]             # 1-based threshold year

            frames.append(pd.DataFrame({
                'simulation_id':         sim_rep + 1,
                'year':                  yr_rep,
                'well_id':               well_ids[well_rep],
                'well_type':             well_types[well_rep],
                'component':             comp_name,
                'display_name':          display_name,
                'barrier_class':         barrier_class,
                'failure_mode':          failure_mode,
                'severity':              severity,
                'trigger_type':          'preventive',
                'sampled_mttf':          mttf[sim_rep, well_rep],
                'base_probability':      base_prob[sim_rep, well_rep],
                'lifecycle_multiplier':  lc_mult[well_rep, yr_rep - 1],
                'adjusted_probability':  adj_prob[sim_rep, well_rep, yr_rep - 1],
                'intervention_required': True,
                'intervention_type':     intervention_type,
                'immediate_or_deferred': 'deferred',
                'estimated_duration_days': duration,
                'estimated_cost':        cost * 0.80,
                'injection_impact':      has_injection_impact,
                'sampled_p10_mttf':                P10,
                'sampled_p50_mttf':                (P10 + P90) / 2.0,
                'sampled_p90_mttf':                P90,
                'cumulative_failure_probability':  cum_fp_3d[sim_rep, well_rep, yr_rep - 1],
                'bernoulli_draw':                  np.nan,
                'failure_occurred':                False,
                'detected':                        False,
                'detection_probability':           detection_prob,
                'threshold_triggered':             True,
                'start_age':                       start_ages[well_rep],
                'effective_year':                  yr_rep + start_ages[well_rep],
            }))

    if not frames:
        return pd.DataFrame(columns=_OUTPUT_COLUMNS)

    df = pd.concat(frames, ignore_index=True)

    # When a preventive event and a reactive failure coincide for the same
    # (sim, well, component, year), keep the preventive one — the inspection
    # would have caught the defect before it became an emergency.
    has_both = df.duplicated(
        subset=['simulation_id', 'well_id', 'component', 'year'], keep=False
    )
    if has_both.any():
        dup_df = df[has_both].copy()
        dup_df['_rank'] = (dup_df['trigger_type'] == 'preventive').astype(int)
        keep_idx = dup_df.groupby(
            ['simulation_id', 'well_id', 'component', 'year']
        )['_rank'].idxmax()
        non_dup_idx = df.index[~has_both]
        df = df.loc[non_dup_idx.union(keep_idx)].reset_index(drop=True)

    # ── APM cross-component detection boost ───────────────────────────────────
    # When the Annular Pressure Monitor (SCP/APB) is functioning in a given
    # (sim, well, year) it converts some previously-undetected cement_barrier
    # and casing reactive failures to planned preventive events.
    # The APM is "not functioning" in a year when it has itself failed that year.
    # Conditional probability: P(detect | APM active, not detected by baseline)
    #   = (boost_prob - base_prob) / (1 - base_prob)
    apm_present = 'annular_pressure_monitor' in df['component'].values
    sensitive_present = bool(_APM_SENSITIVE & set(df['component'].unique()))
    if apm_present and sensitive_present:
        apm_rows = df[df['component'] == 'annular_pressure_monitor']
        apm_failed_keys = set(
            zip(apm_rows['simulation_id'], apm_rows['well_id'], apm_rows['year'])
        )
        target_mask = (
            df['component'].isin(_APM_SENSITIVE)
            & (df['trigger_type'] == 'reactive')
            & (~df['detected'])
            & (~df['threshold_triggered'])
        )
        target_idx = df.index[target_mask]
        if len(target_idx) > 0:
            rows = df.loc[target_idx]
            event_keys = list(zip(rows['simulation_id'], rows['well_id'], rows['year']))
            apm_functioning = [k not in apm_failed_keys for k in event_keys]
            boost_idx = target_idx[apm_functioning]
            for comp, boost_prob in _APM_BOOST.items():
                comp_idx = boost_idx[df.loc[boost_idx, 'component'] == comp]
                if len(comp_idx) == 0:
                    continue
                base = df.loc[comp_idx, 'detection_probability'].values
                cond = np.clip((boost_prob - base) / np.maximum(1.0 - base, 1e-6), 0.0, 1.0)
                newly_detected = comp_idx[rng.random(len(comp_idx)) < cond]
                if len(newly_detected) > 0:
                    df.loc[newly_detected, 'detected'] = True
                    df.loc[newly_detected, 'trigger_type'] = 'preventive'
                    df.loc[newly_detected, 'immediate_or_deferred'] = 'deferred'
                    df.loc[newly_detected, 'estimated_cost'] *= 0.80
                    df.loc[newly_detected, 'detection_probability'] = boost_prob

    return df
