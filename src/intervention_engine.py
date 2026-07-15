"""
Intervention decision engine.

Applies barrier hierarchy and escalation rules to the raw failure event log.

Barrier classes:
  safety        -- TRSV, Cement, Casing
  production    -- Tubing, Packer, Wellhead, Tree -> can batch
  monitoring    -- Gauge, Fiber Optics -> deferrable
  flow_assurance -- Injectivity sub-modes -> rigless first; persistent
                    formation-damage modes escalate on repeat failures

Barrier hierarchy (applies to REACTIVE failures only):
  safety reactive    -> always immediate (undetected failures require emergency response)
  safety preventive  -> stays deferred  (planned inspection, not an emergency)
  monitoring         -> always deferrable regardless of trigger type

Escalation rule:
  >= 2 medium/high-severity REACTIVE failures within any 3-year window on
  the same well -> promote that well's remaining reactive deferred events to
  immediate. Preventive events are never escalated (they are already planned).
"""
import pandas as pd

# Flow-assurance modes that escalate rigless -> full workover on repeat
# failures of the SAME mode on the same well (persistent formation damage).
# hydrate_control is excluded: hydrate events are operational (startup /
# shutdown driven), remediated at the wellhead, and recur by design — a
# repeat hydrate never justifies a rig workover.
# ('injectivity' retained for backward compat with pre-split assumption CSVs.)
FA_ESCALATABLE = {'injectivity', 'halite_plugging', 'carbonate_scaling',
                  'microbial_plugging'}


def apply_intervention_decisions(
    failure_df: pd.DataFrame,
    escalation_window: int = 3,
    escalation_threshold: int = 2,
) -> pd.DataFrame:
    if failure_df.empty:
        return failure_df

    df = failure_df.copy()

    # -- Step 1: Barrier-hierarchy overrides ----------------------------------
    # Only REACTIVE safety failures are forced to immediate. Preventive safety
    # events (caught by inspection / monitoring) remain planned and deferrable.
    safety_reactive_mask = (
        (df['barrier_class'] == 'safety') & (df['trigger_type'] == 'reactive')
    )
    df.loc[safety_reactive_mask, 'immediate_or_deferred'] = 'immediate'

    # Monitoring barriers are always deferrable regardless of trigger type.
    monitoring_mask = df['barrier_class'] == 'monitoring'
    df.loc[monitoring_mask, 'immediate_or_deferred'] = 'deferred'

    # -- Step 2: Flow-assurance escalation -- rigless first, then workover ----
    # Repeat failures of the same persistent mode on the same well escalate.
    # Sort by year so "repeat" is chronological — reactive and threshold-
    # preventive events are generated in separate frames, so raw row order
    # does not follow event time.
    fa_mask = df['component'].isin(FA_ESCALATABLE)
    if fa_mask.any():
        fa = df[fa_mask].sort_values('year', kind='stable')
        fa_repeat = fa.groupby(['simulation_id', 'well_id', 'component']).cumcount()
        escalate_idx = fa.index[fa_repeat >= 1]
        df.loc[escalate_idx, 'intervention_type'] = 'full_workover'
        df.loc[escalate_idx, 'immediate_or_deferred'] = 'deferred'

    # -- Step 3: Multi-failure escalation rule --------------------------------
    # Only applies to reactive events. Escalation shortens deferral priority
    # for reactive non-safety events on the affected well, but does NOT touch
    # preventive events (those are already optimally scheduled).
    escalated_pairs = _find_escalated_wells(df, escalation_window, escalation_threshold)
    if escalated_pairs:
        df['_pair'] = list(zip(df['simulation_id'], df['well_id']))
        is_escalated = df['_pair'].isin(escalated_pairs)
        is_reactive  = df['trigger_type'] == 'reactive'
        is_deferred  = df['immediate_or_deferred'] == 'deferred'
        is_non_safety = df['barrier_class'] != 'safety'
        df.loc[is_escalated & is_reactive & is_deferred & is_non_safety,
               'immediate_or_deferred'] = 'immediate'
        df['escalated'] = is_escalated & is_reactive
        df.drop(columns=['_pair'], inplace=True)
    else:
        df['escalated'] = False

    return df


def _find_escalated_wells(df: pd.DataFrame, window: int, threshold: int) -> set:
    # Only count reactive medium/high failures for the escalation trigger
    medium_high = df[
        (df['severity'].isin(['medium', 'high'])) & (df['trigger_type'] == 'reactive')
    ]
    if medium_high.empty:
        return set()

    year_lists = (
        medium_high.groupby(['simulation_id', 'well_id'])['year']
        .apply(sorted)
        .reset_index()
    )

    escalated = set()
    for _, row in year_lists.iterrows():
        years = row['year']
        for i, start_yr in enumerate(years):
            count = sum(1 for y in years[i:] if y <= start_yr + window)
            if count >= threshold:
                escalated.add((row['simulation_id'], row['well_id']))
                break

    return escalated
