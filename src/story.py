"""
Engineering story layer for CCS Workover Forecast.

Transforms raw simulation outputs into human-readable narratives,
decision paths, component health series, and Sankey flow data.

All functions are pure consumers of existing simulation outputs.
No new simulation logic; no new probability calculations.
"""
import os as _os
import pandas as pd

# ── Display constants ─────────────────────────────────────────────────────────

BARRIER_ICON = {
    'safety':         '🔴',
    'production':     '🟠',
    'monitoring':     '🟢',
    'flow_assurance': '🔵',
}
BARRIER_COLOR = {
    'safety':         '#ef4444',
    'production':     '#f59e0b',
    'monitoring':     '#22c55e',
    'flow_assurance': '#3b82f6',
}
TRIGGER_ICON = {
    'reactive':   '⚠️',
    'preventive': '✅',
    'seismic':    '🌋',
}
CAMPAIGN_ICON = {
    'emergency':     '🚨',
    'immediate':     '⚡',
    'deferred_batch': '📅',
    'end_of_life':   '🏁',
}
INTERV_LABEL = {
    'full_workover':        'Full Workover',
    'light_intervention':   'Light Intervention',
    'rigless_intervention': 'Rigless Intervention',
}


def _fmt_cost(v) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return '—'
    if pd.isna(v) or v == 0:
        return '—'
    if v >= 1_000_000:
        return f'${v / 1_000_000:.1f}M'
    if v >= 1_000:
        return f'${v / 1_000:.0f}k'
    return f'${v:.0f}'


# ── Rejuvenation rules ────────────────────────────────────────────────────────

def _load_rejuvenation_rules() -> pd.DataFrame:
    """Load rejuvenation_rules.csv; return empty DataFrame if not found."""
    path = _os.path.normpath(
        _os.path.join(_os.path.dirname(__file__), '..', 'data', 'assumptions', 'rejuvenation_rules.csv')
    )
    try:
        return pd.read_csv(path)
    except FileNotFoundError:
        return pd.DataFrame(columns=[
            'component', 'intervention_type', 'rejuvenation_factor', 'post_intervention_health_cap'
        ])


def _post_intervention_health(
    health_pre: float,
    comp: str,
    interv_type: str,
    rejuv_df: pd.DataFrame,
) -> float:
    """
    Compute post-intervention health using component-specific rejuvenation factor.
    rejuvenation_factor=0.0 → repaired to as-new (full restoration).
    rejuvenation_factor=1.0 → repaired to as-old (no health gain).
    """
    if rejuv_df is None or rejuv_df.empty:
        return 100.0
    mask = (rejuv_df['component'] == comp) & (rejuv_df['intervention_type'] == interv_type)
    if not mask.any():
        mask = rejuv_df['component'] == comp
    if not mask.any():
        return 100.0
    rule = rejuv_df[mask].iloc[0]
    rf  = float(rule['rejuvenation_factor'])
    cap = float(rule['post_intervention_health_cap'])
    # Linear interpolation between pre-health (rf=1) and 100% (rf=0)
    restored = health_pre + (1.0 - rf) * (100.0 - health_pre)
    return round(min(cap, restored), 1)


# Flow-assurance modes whose repeat failures escalate rigless -> workover
# (mirrors intervention_engine.FA_ESCALATABLE; hydrate_control never escalates)
_FA_ESCALATABLE = {'injectivity', 'halite_plugging', 'carbonate_scaling',
                   'microbial_plugging'}

# Components where full_workover is required by design (not escalation)
_INHERENTLY_WORKOVER_NOTE = {
    'fiber_optics':  'Fiber optic cable is installed with the tubing string — retrieval requires a full rig workover by design.',
    'control_line':  'Hydraulic control line runs with the tubing string — replacement requires a full tubing pull.',
    'tubing_hanger': 'Tubing hanger seal access requires retrieving the full tubing string.',
}

_BARRIER_DRIVER_MAP = {
    'safety':         'Safety barrier integrity',
    'production':     'Production barrier lifecycle',
    'monitoring':     'Monitoring sensor availability',
    'flow_assurance': 'Flow assurance / injectivity',
}


# ── Event Story Card ──────────────────────────────────────────────────────────

def build_event_story_card(row: pd.Series) -> dict:
    """
    Generate a human-readable story card for one simulation trace row.
    Returns a dict of text fields ready for UI rendering.
    """
    comp     = str(row.get('display_name', row.get('component', 'Unknown')))
    comp_key = str(row.get('component', ''))
    year_f   = int(row.get('year_of_field_life', 0))
    cal_yr   = int(row.get('calendar_year', year_f))
    try:
        _eff = row.get('effective_year')
        eff_yr = int(_eff) if pd.notna(_eff) else year_f
    except (TypeError, ValueError):
        eff_yr = year_f
    barrier  = str(row.get('barrier_class', ''))
    trigger  = str(row.get('trigger_type', ''))
    fail_occ = bool(row.get('failure_occurred', False))
    detected = bool(row.get('detected', False))
    thresh   = bool(row.get('threshold_triggered', False))
    interv   = str(row.get('intervention_type', ''))
    escalated = bool(row.get('escalated', False))
    draw     = row.get('bernoulli_draw')
    fp       = row.get('annual_failure_probability')
    cum_fp   = row.get('cumulative_failure_probability')
    btub     = row.get('bathtub_multiplier', 1.0)
    campaign = row.get('campaign_id')
    camp_t   = row.get('campaign_type', '—')
    camp_sz  = row.get('campaign_size')
    cost     = row.get('intervention_cost', 0)
    downtime = row.get('downtime_days', 0)
    can_def  = bool(row.get('can_defer', False))

    # ── What happened ──────────────────────────────────────────────────────────
    if thresh:
        what = (
            f"{comp} cumulative failure probability reached the preventive intervention threshold. "
            "A planned intervention was scheduled before any reactive failure occurred."
        )
    elif trigger == 'seismic':
        what = (
            f"A field-level seismic event in year {year_f} subjected {comp} to transient "
            "shock and shear loading, causing failure. "
            + ("Post-event inspection (stoplight protocol) identified the damage before "
               "leakage escalated — the response was executed as a planned intervention."
               if detected else
               "The damage was not identified by post-event inspection and required an "
               "unplanned emergency response.")
        )
    elif fail_occ and detected:
        what = (
            f"Monitoring detected early-stage degradation in {comp} before functional failure. "
            "The event was reclassified from reactive to a planned intervention, "
            "reducing response cost by 20%."
        )
    elif fail_occ and not detected:
        what = (
            f"{comp} experienced a reactive failure not intercepted by the monitoring layer. "
            "An unplanned intervention was required."
        )
    else:
        what = f"A preventive intervention was triggered for {comp}."

    # ── Why did it happen ──────────────────────────────────────────────────────
    parts = []
    if pd.notna(fp):
        parts.append(f"annual failure probability was {float(fp) * 100:.1f}%")
    if pd.notna(btub) and float(btub) != 1.0:
        phase = 'infant mortality' if eff_yr <= 3 else 'wear-out'
        phase_at = f'{phase} phase' if eff_yr == year_f else f'{phase} phase at well age {eff_yr}'
        parts.append(f"the bathtub multiplier was {float(btub):.2f}× ({phase_at})")
    if pd.notna(cum_fp):
        parts.append(f"cumulative failure probability had reached {float(cum_fp) * 100:.1f}%")
    if pd.notna(draw) and pd.notna(fp):
        try:
            if float(draw) < float(fp):
                parts.append(
                    f"the Bernoulli draw ({float(draw):.4f}) fell below "
                    f"the failure probability ({float(fp):.4f})"
                )
        except (TypeError, ValueError):
            pass
    if parts:
        why = 'The ' + parts[0]
        for p in parts[1:]:
            why += f'; {p}'
        why = why[0].upper() + why[1:] + '.'
    else:
        why = 'Model probability thresholds were exceeded.'

    # ── Detection ──────────────────────────────────────────────────────────────
    if thresh:
        detection_txt = (
            "Not applicable — this was a threshold-triggered preventive event. "
            "No reactive failure occurred; the intervention was scheduled proactively."
        )
    elif trigger == 'seismic':
        detection_txt = (
            "Yes. The seismic monitoring array flagged the event and the mandatory "
            "post-event inspection (40 CFR §146.89) located the damage — response "
            "rescheduled as a planned intervention at 80% of reactive cost."
            if detected else
            "No. Seismic damage is sudden and subsurface — without a functioning "
            "seismic monitoring array on this well, post-event detection probability "
            "is only 10%."
        )
    elif detected:
        detection_txt = (
            "Yes. The monitoring programme intercepted the degradation before functional failure, "
            "allowing it to be rescheduled as a planned intervention at 80% of reactive cost."
        )
    else:
        detection_txt = "No. The failure escalated before the monitoring layer could detect it."

    # ── Emergency assessment ───────────────────────────────────────────────────
    if trigger in ('reactive', 'seismic') and not detected and barrier == 'safety':
        emergency_txt = (
            ("Yes. An undetected seismic safety-barrier failure requires an immediate "
             "emergency response — rig mobilisation cannot be deferred.")
            if trigger == 'seismic' else
            ("Yes. A reactive safety-barrier failure requires an immediate emergency response — "
             "rig mobilisation cannot be deferred.")
        )
    elif can_def:
        emergency_txt = "No. The intervention was deferred into a planned campaign, sharing mobilisation cost."
    else:
        emergency_txt = (
            "No emergency, but the intervention required immediate execution "
            "(non-safety barrier, non-deferrable by barrier hierarchy)."
        )

    # ── Intervention type context note ────────────────────────────────────────
    interv_note = ''
    if interv == 'full_workover' and comp_key in _INHERENTLY_WORKOVER_NOTE:
        interv_note = _INHERENTLY_WORKOVER_NOTE[comp_key]
    elif interv == 'full_workover' and comp_key in _FA_ESCALATABLE:
        interv_note = (
            'Escalated from rigless to full workover (repeat failure of this '
            'flow-assurance mode on this well).'
        )

    # ── Campaign summary ───────────────────────────────────────────────────────
    camp_str = str(campaign) if campaign is not None else ''
    if camp_str and camp_str not in ('nan', '<NA>', 'None', ''):
        ci = CAMPAIGN_ICON.get(str(camp_t), '📌')
        sz = f"{int(float(camp_sz))} wells" if pd.notna(camp_sz) else "?"
        camp_label = f"{ci} {campaign}  ·  {str(camp_t).replace('_', ' ').title()}  ·  {sz}"
    else:
        camp_label = "Not yet assigned to a campaign"

    try:
        dt_str = f"{int(float(downtime))} days" if pd.notna(downtime) and float(downtime) > 0 else '—'
    except (TypeError, ValueError):
        dt_str = '—'

    return {
        'year_field':     year_f,
        'cal_year':       cal_yr,
        'component':      comp,
        'barrier':        barrier,
        'barrier_icon':   BARRIER_ICON.get(barrier, '⚪'),
        'barrier_color':  BARRIER_COLOR.get(barrier, '#64748b'),
        'trigger':        trigger,
        'trigger_icon':   TRIGGER_ICON.get(trigger, '❓'),
        'what':           what,
        'why':            why,
        'detection':      detection_txt,
        'emergency':      emergency_txt,
        'campaign':       camp_label,
        'cost':           _fmt_cost(cost),
        'downtime':       dt_str,
        'intervention':   INTERV_LABEL.get(interv, interv.replace('_', ' ').title()),
        'thresh':            thresh,
        'fail_occ':          fail_occ,
        'detected':          detected,
        'intervention_note': interv_note,
    }


# ── Decision Path ─────────────────────────────────────────────────────────────

def build_decision_path(row: pd.Series) -> list:
    """
    Return an ordered list of decision-node dicts for the Decision Path view.
    Each node: {label, value, detail, outcome, color}
    """
    draw    = row.get('bernoulli_draw')
    fp      = row.get('annual_failure_probability')
    cum_fp  = row.get('cumulative_failure_probability')
    btub    = row.get('bathtub_multiplier', 1.0)
    thresh  = bool(row.get('threshold_triggered', False))
    fail    = bool(row.get('failure_occurred', False))
    det     = bool(row.get('detected', False))
    barrier = str(row.get('barrier_class', ''))
    defer   = bool(row.get('can_defer', False))
    camp    = row.get('campaign_id')
    camp_t  = row.get('campaign_type', '—')
    interv  = str(row.get('intervention_type', ''))
    thr_pct = row.get('detection_probability', 0.9)

    RED, AMBER, GREEN, BLUE, PURPLE, GREY = (
        '#ef4444', '#f59e0b', '#22c55e', '#3b82f6', '#8b5cf6', '#64748b'
    )

    nodes = []

    # 1 — Annual failure probability
    fp_val = None
    try:
        fp_val = float(fp) if pd.notna(fp) else None
    except (TypeError, ValueError):
        pass
    fp_color = RED if (fp_val and fp_val > 0.15) else (AMBER if (fp_val and fp_val > 0.08) else GREEN)
    btub_val = 1.0
    try:
        btub_val = float(btub) if pd.notna(btub) else 1.0
    except (TypeError, ValueError):
        pass
    nodes.append({
        'label':  'Annual Failure Probability',
        'value':  f'{fp_val * 100:.2f}%' if fp_val is not None else 'N/A',
        'detail': f'Eff. MTTF → base prob × bathtub {btub_val:.3f}× → adjusted annual prob',
        'color':  fp_color,
    })

    # 2 — Failure event
    if thresh:
        cf_val = None
        try:
            cf_val = float(cum_fp) if pd.notna(cum_fp) else None
        except (TypeError, ValueError):
            pass
        try:
            thr_disp = f'{float(thr_pct) * 100:.0f}%'
        except (TypeError, ValueError):
            thr_disp = '90%'
        nodes.append({
            'label':   'Cumulative Failure Probability',
            'value':   f'{cf_val * 100:.1f}%' if cf_val is not None else 'N/A',
            'detail':  f'Exceeded intervention threshold',
            'outcome': 'THRESHOLD EXCEEDED → PREVENTIVE TRIGGER',
            'color':   PURPLE,
        })
    else:
        draw_val = None
        try:
            draw_val = float(draw) if pd.notna(draw) else None
        except (TypeError, ValueError):
            pass
        if draw_val is not None and fp_val is not None:
            result_color = RED if fail else GREEN
            nodes.append({
                'label':   'Bernoulli Trial',
                'value':   f'Draw = {draw_val:.4f}',
                'detail':  f'{"draw < prob → FAILURE" if fail else "draw ≥ prob → no failure this year"}',
                'outcome': 'FAILURE' if fail else 'NO FAILURE',
                'color':   result_color,
            })

    # 3 — Detection (reactive failures only)
    if fail and not thresh:
        det_color = GREEN if det else AMBER
        nodes.append({
            'label':  'Monitoring Detection',
            'value':  'DETECTED' if det else 'NOT DETECTED',
            'detail': ('Reclassified preventive — cost ×0.8, response deferred'
                       if det else 'Remains reactive — immediate or urgent response required'),
            'color':  det_color,
        })

    # 4 — Barrier class
    bc_color = BARRIER_COLOR.get(barrier, GREY)
    barrier_interp = {
        'safety':         'Safety barriers require immediate response when reactive',
        'production':     'Production barriers may be batched into deferred campaigns',
        'monitoring':     'Monitoring barriers are always deferrable regardless of trigger',
        'flow_assurance': 'Flow assurance follows rigless-first escalation (repeat → workover)',
    }
    nodes.append({
        'label':  'Barrier Class',
        'value':  BARRIER_ICON.get(barrier, '⚪') + '  ' + barrier.replace('_', ' ').title(),
        'detail': barrier_interp.get(barrier, ''),
        'color':  bc_color,
    })

    # 5 — Deferral decision
    defer_color = GREEN if defer else AMBER
    nodes.append({
        'label':  'Deferral Decision',
        'value':  'DEFERRED' if defer else 'IMMEDIATE',
        'detail': ('Added to campaign batching queue — rig mobilisation shared across wells'
                   if defer else 'Requires immediate or standalone campaign mobilisation'),
        'color':  defer_color,
    })

    # 6 — Campaign assignment
    camp_str = str(camp) if camp is not None else ''
    if camp_str and camp_str not in ('nan', '<NA>', 'None', ''):
        ci = CAMPAIGN_ICON.get(str(camp_t), '📌')
        nodes.append({
            'label':  'Campaign Assignment',
            'value':  camp_str,
            'detail': f'{ci} {str(camp_t).replace("_", " ").title()}',
            'color':  BLUE,
        })

    # 7 — Intervention executed
    nodes.append({
        'label':  'Intervention Executed',
        'value':  INTERV_LABEL.get(interv, interv.replace('_', ' ').title()),
        'detail': '',
        'color':  BLUE,
    })

    for n in nodes:
        n.setdefault('outcome', '')
        n.setdefault('detail', '')

    return nodes


# ── Well Journey ──────────────────────────────────────────────────────────────

def build_well_journey(
    simulation_trace: pd.DataFrame,
    campaign_log: pd.DataFrame,
    sim_id: int,
    well_id: str,
    first_injection_year: int,
    operating_years: int,
) -> dict:
    """
    Assemble all data needed to render the Well Journey for one (sim, well) pair.
    Consumes simulation_trace and campaign_log only.
    """
    wt = simulation_trace[
        (simulation_trace['simulation_id'] == sim_id) &
        (simulation_trace['well_id'] == well_id)
    ].sort_values(['year_of_field_life', 'component']).copy()

    if wt.empty:
        return {}

    rejuv_df     = _load_rejuvenation_rules()
    story_cards  = [build_event_story_card(row) for _, row in wt.iterrows()]
    health_df    = _build_health_series(wt, operating_years, first_injection_year, rejuv_df)
    cfact_df     = _build_counterfactual_health(wt, operating_years, first_injection_year)
    rul_df       = _build_rul_table(wt, health_df, first_injection_year, operating_years)

    has_cost = 'intervention_cost' in wt.columns
    has_dt   = 'downtime_days'     in wt.columns
    cost_by_year = (
        wt.assign(
            cost    =wt['intervention_cost'].fillna(0) if has_cost else 0.0,
            downtime=wt['downtime_days'].fillna(0)     if has_dt   else 0.0,
        )
        .groupby('year_of_field_life')[['cost', 'downtime']].sum()
        .reset_index()
    )
    cost_by_year['calendar_year'] = first_injection_year + cost_by_year['year_of_field_life'] - 1

    total_cost     = float(wt['intervention_cost'].sum()) if has_cost else 0.0
    total_downtime = float(wt['downtime_days'].sum())     if has_dt   else 0.0
    n_reactive     = int(wt['trigger_type'].isin(('reactive', 'seismic')).sum()) if 'trigger_type' in wt.columns else 0
    n_preventive   = int((wt['trigger_type'] == 'preventive').sum()) if 'trigger_type' in wt.columns else 0
    n_seismic      = int((wt['trigger_type'] == 'seismic').sum())    if 'trigger_type' in wt.columns else 0
    ct_col         = wt.get('campaign_type', pd.Series(dtype=str))
    n_emergency    = int((ct_col == 'emergency').sum())
    peak_cost_yr   = (
        int(cost_by_year.loc[cost_by_year['cost'].idxmax(), 'year_of_field_life'])
        if not cost_by_year.empty and cost_by_year['cost'].max() > 0
        else 0
    )

    return {
        'sim_id':                   sim_id,
        'well_id':                  well_id,
        'wt':                       wt,
        'story_cards':              story_cards,
        'health_df':                health_df,
        'counterfactual_health_df': cfact_df,
        'rul_df':                   rul_df,
        'cost_by_year':             cost_by_year,
        'n_interventions':          len(wt),
        'n_reactive':               n_reactive,
        'n_preventive':             n_preventive,
        'n_seismic':                n_seismic,
        'n_emergency':              n_emergency,
        'total_cost':               total_cost,
        'total_downtime':           total_downtime,
        'peak_cost_year':           peak_cost_yr,
    }


def _build_health_series(
    wt: pd.DataFrame,
    operating_years: int,
    first_injection_year: int,
    rejuvenation_rules=None,
) -> pd.DataFrame:
    """
    Build component health % evolution from trace data.

    Health at each event year = (1 - cumulative_failure_probability) × 100.
    After each intervention the component is restored using component-specific
    rejuvenation factors (not always 100%).
    Between known points the series is linearly interpolated for readability.
    This is a visualisation of existing reliability data, not new physics.
    """
    if 'cumulative_failure_probability' not in wt.columns:
        return pd.DataFrame()

    components = wt['component'].unique()
    rows = []

    for comp in components:
        ce = wt[wt['component'] == comp].sort_values('year_of_field_life')
        display = str(ce['display_name'].iloc[0]) if 'display_name' in ce.columns else comp

        # Build (year_float, health_pct) anchor list
        anchors = [(0.0, 100.0)]

        for _, ev in ce.iterrows():
            yr = float(ev['year_of_field_life'])
            try:
                cf = float(ev['cumulative_failure_probability'])
                health_pre = max(0.0, (1.0 - cf) * 100.0) if not pd.isna(cf) else max(0.0, anchors[-1][1] - 3.0)
            except (TypeError, ValueError):
                health_pre = max(0.0, anchors[-1][1] - 3.0)

            anchors.append((yr, health_pre))
            interv_t = str(ev.get('intervention_type', ''))
            post_h = _post_intervention_health(health_pre, comp, interv_t, rejuvenation_rules)
            anchors.append((yr + 0.3, post_h))

        # Extend to end of life with gentle decay
        last_yr, last_h = anchors[-1]
        if last_yr < operating_years:
            end_h = max(0.0, last_h - (operating_years - last_yr) * 1.2)
            anchors.append((float(operating_years), end_h))

        for yr_f, h in anchors:
            rows.append({
                'component':          comp,
                'display_name':       display,
                'year_of_field_life': yr_f,
                'calendar_year':      first_injection_year + yr_f - 1,
                'health_pct':         round(h, 1),
            })

    return pd.DataFrame(rows)


# ── Counterfactual health (no-intervention scenario) ─────────────────────────

def _build_counterfactual_health(
    wt: pd.DataFrame,
    operating_years: int,
    first_injection_year: int,
) -> pd.DataFrame:
    """
    Illustrative health path if no interventions had ever occurred.
    Health degrades from each failure event without any post-intervention recovery.
    Labelled 'Illustrative counterfactual — not a re-simulation.'
    """
    if 'cumulative_failure_probability' not in wt.columns:
        return pd.DataFrame()

    components = wt['component'].unique()
    rows = []

    for comp in components:
        ce = wt[wt['component'] == comp].sort_values('year_of_field_life')
        display = str(ce['display_name'].iloc[0]) if 'display_name' in ce.columns else comp

        anchors = [(0.0, 100.0)]
        last_pre = 100.0

        for _, ev in ce.iterrows():
            yr = float(ev['year_of_field_life'])
            try:
                cf = float(ev['cumulative_failure_probability'])
                # Counterfactual cumulative probability relative to no-intervention start
                health_pre = max(0.0, (1.0 - cf) * last_pre) if not pd.isna(cf) else max(0.0, last_pre - 3.0)
            except (TypeError, ValueError):
                health_pre = max(0.0, last_pre - 3.0)
            anchors.append((yr, health_pre))
            last_pre = health_pre   # no recovery — stay at degraded level

        last_yr, last_h = anchors[-1]
        if last_yr < operating_years:
            end_h = max(0.0, last_h - (operating_years - last_yr) * 1.5)
            anchors.append((float(operating_years), end_h))

        for yr_f, h in anchors:
            rows.append({
                'component':          comp,
                'display_name':       display,
                'year_of_field_life': yr_f,
                'calendar_year':      first_injection_year + yr_f - 1,
                'health_pct':         round(h, 1),
            })

    return pd.DataFrame(rows)


# ── Remaining Useful Life table ───────────────────────────────────────────────

def _build_rul_table(
    wt: pd.DataFrame,
    health_df: pd.DataFrame,
    first_injection_year: int,
    operating_years: int,
) -> pd.DataFrame:
    """
    Build a per-component Remaining Useful Life (RUL) table.
    Estimates are approximate — based on last observed annual failure probability,
    not a re-simulation. Clearly labelled as indicative.
    """
    if wt.empty or health_df.empty:
        return pd.DataFrame()

    rows = []
    for comp in wt['component'].unique():
        comp_wt  = wt[wt['component'] == comp].sort_values('year_of_field_life')
        comp_hdf = health_df[health_df['component'] == comp].sort_values('year_of_field_life')

        display = str(comp_wt['display_name'].iloc[0]) if 'display_name' in comp_wt.columns else comp
        barrier = str(comp_wt['barrier_class'].iloc[0]) if 'barrier_class' in comp_wt.columns else ''

        last_ev = comp_wt.iloc[-1]
        last_yr_f = int(last_ev['year_of_field_life'])
        last_yr_c = first_injection_year + last_yr_f - 1

        # Post-last-intervention health: first anchor point after (last_yr_f + 0.1)
        post_int = comp_hdf[comp_hdf['year_of_field_life'] > last_yr_f + 0.1]
        if not post_int.empty:
            current_health = float(post_int.iloc[0]['health_pct'])
        elif not comp_hdf.empty:
            current_health = float(comp_hdf.iloc[-1]['health_pct'])
        else:
            current_health = 70.0

        # Approximate RUL using last annual failure probability
        try:
            last_fp = float(last_ev.get('annual_failure_probability', 0.05))
            if pd.isna(last_fp) or last_fp <= 0:
                last_fp = 0.05
        except (TypeError, ValueError):
            last_fp = 0.05

        if current_health > 60.0:
            annual_health_loss = max(0.5, last_fp * 100.0)
            rul_years = (current_health - 60.0) / annual_health_loss
            rul_years = round(min(rul_years, float(operating_years - last_yr_f)), 1)
        else:
            rul_years = 0.0

        next_risk_f = last_yr_f + max(1, int(rul_years))
        next_risk_c = first_injection_year + next_risk_f - 1

        rows.append({
            'Component':            display,
            'Current Health':       f'{current_health:.0f}%',
            'Last Intervention':    f'Yr {last_yr_f} ({last_yr_c})',
            'Est. RUL (yrs)':       rul_years if rul_years > 0 else '<1',
            'Next Risk Window':     f'Yr {next_risk_f} ({next_risk_c})',
            'Primary Driver':       _BARRIER_DRIVER_MAP.get(barrier, barrier.replace('_', ' ').title()),
        })

    return pd.DataFrame(rows)


# ── Campaign Story ────────────────────────────────────────────────────────────

def build_campaign_story(
    campaign_id: str,
    campaign_log: pd.DataFrame,
    simulation_trace: pd.DataFrame,
) -> dict:
    """Build a human-readable story for one campaign."""
    if campaign_log.empty or campaign_id not in campaign_log['campaign_id'].values:
        return {}

    camp     = campaign_log[campaign_log['campaign_id'] == campaign_id].iloc[0]
    yr       = int(camp['campaign_year'])
    ctype    = str(camp['campaign_type'])
    n_wells  = int(camp['n_wells'])
    n_events = int(camp['n_events'])
    mob_cost = float(camp.get('mobilisation_cost', 0))
    int_cost = float(camp.get('intervention_cost', 0))
    total    = float(camp.get('total_campaign_cost', int_cost + mob_cost))
    n_rig    = int(camp.get('n_rig_workovers', 0))
    mob_savings = max(0.0, n_rig - 1) * mob_cost

    ctype_reasons = {
        'emergency':     'A safety-critical reactive failure required immediate rig mobilisation.',
        'immediate':     'Multiple urgent interventions in the same year were consolidated to share mobilisation cost.',
        'deferred_batch': (
            f'{n_events} deferred interventions accumulated until the campaign threshold '
            'was reached, triggering a planned batch deployment.'
        ),
        'end_of_life':   'Remaining deferred interventions were cleared at end of the operating lifecycle.',
    }
    why = ctype_reasons.get(ctype, 'Campaign triggered by intervention scheduling logic.')

    if 'campaign_id' in simulation_trace.columns:
        ev = simulation_trace[simulation_trace['campaign_id'] == campaign_id]
        dn = 'display_name' if 'display_name' in ev.columns else 'component'
        wells_in = sorted(ev['well_id'].unique().tolist())
        comps_in = sorted(ev[dn].unique().tolist())
    else:
        wells_in, comps_in = [], []

    if ctype == 'emergency':
        avoidable = (
            "Not easily avoidable — reactive safety-barrier failures require immediate response. "
            "Enhanced monitoring could convert similar future events to planned interventions (20% cost saving)."
        )
    elif ctype in ('deferred_batch', 'end_of_life'):
        save_str = _fmt_cost(mob_savings)
        avoidable = (
            f"By design — batching deferred interventions is the optimal scheduling outcome. "
            + (f"This campaign saved an estimated {save_str} in avoided rig mobilisation costs. " if mob_savings > 0 else "")
        )
    else:
        avoidable = "Potentially reducible by adjusting the campaign threshold or maximum deferral window."

    narrative_parts = [
        f"Campaign **{campaign_id}** was a **{ctype.replace('_', ' ')} campaign** "
        f"executed in Year {yr}. "
        f"It addressed {n_events} intervention event{'s' if n_events > 1 else ''} "
        f"across {n_wells} well{'s' if n_wells > 1 else ''}."
    ]
    if mob_savings > 0:
        narrative_parts.append(
            f"Batching saved approximately **{_fmt_cost(mob_savings)}** in avoided rig mobilisation "
            f"— equivalent to {n_rig - 1} standalone mobilisation{'s' if n_rig - 1 > 1 else ''} avoided."
        )
    if ctype == 'deferred_batch' and n_events > 2:
        narrative_parts.append(
            f"Without campaign batching, these {n_events} events would have required "
            f"up to {n_events} separate rig deployments."
        )

    return {
        'campaign_id':       campaign_id,
        'year':              yr,
        'campaign_type':     ctype,
        'campaign_icon':     CAMPAIGN_ICON.get(ctype, '📌'),
        'n_wells':           n_wells,
        'n_events':          n_events,
        'n_rig_workovers':   n_rig,
        'mobilisation_cost': mob_cost,
        'intervention_cost': int_cost,
        'total_cost':        total,
        'mob_savings':       mob_savings,
        'why':               why,
        'avoidable':         avoidable,
        'wells':             wells_in,
        'components':        comps_in,
        'narrative':         ' '.join(narrative_parts),
    }


# ── Portfolio Sankey ──────────────────────────────────────────────────────────

def build_sankey_data(
    simulation_trace: pd.DataFrame,
    n_simulations: int,
) -> dict:
    """
    Compute Sankey diagram flow data from the simulation trace.
    All flow values are per-simulation averages.
    """
    if simulation_trace.empty:
        return {}

    t   = simulation_trace.copy()
    n_s = max(1, n_simulations)

    def avg(mask):
        return round(float(mask.sum()) / n_s, 1)

    det_s  = t['detected'].astype(bool)          if 'detected'          in t.columns else pd.Series(False, index=t.index)
    prev_s = t['trigger_type'] == 'preventive'   if 'trigger_type'      in t.columns else pd.Series(False, index=t.index)
    def_s  = t['can_defer'].astype(bool)         if 'can_defer'         in t.columns else pd.Series(False, index=t.index)
    ct_s   = t['campaign_type'].fillna('')        if 'campaign_type'     in t.columns else pd.Series('', index=t.index)
    it_s   = t['intervention_type'].fillna('')    if 'intervention_type' in t.columns else pd.Series('', index=t.index)

    labels = [
        'All Events',           # 0
        'Detected',             # 1
        'Undetected',           # 2
        'Preventive',           # 3
        'Reactive',             # 4
        'Deferred',             # 5
        'Immediate',            # 6
        'Deferred Batch',       # 7
        'Emergency',            # 8
        'Urgent',               # 9
        'End of Life',          # 10
        'Full Workover',        # 11
        'Light Intervention',   # 12
        'Rigless Intervention', # 13
    ]
    IDX = {lbl: i for i, lbl in enumerate(labels)}

    srcs, tgts, vals, lcolors = [], [], [], []

    def link(s, tl, val, color='rgba(100,116,139,0.3)'):
        if val <= 0:
            return
        srcs.append(IDX[s])
        tgts.append(IDX[tl])
        vals.append(val)
        lcolors.append(color)

    link('All Events', 'Detected',   avg(det_s),  'rgba(34,197,94,0.3)')
    link('All Events', 'Undetected', avg(~det_s), 'rgba(239,68,68,0.3)')

    link('Detected',   'Preventive', avg(det_s  &  prev_s), 'rgba(34,197,94,0.3)')
    link('Detected',   'Reactive',   avg(det_s  & ~prev_s), 'rgba(245,158,11,0.3)')
    link('Undetected', 'Reactive',   avg(~det_s & ~prev_s), 'rgba(239,68,68,0.3)')
    link('Undetected', 'Preventive', avg(~det_s &  prev_s), 'rgba(148,163,184,0.3)')

    link('Preventive', 'Deferred',  avg(prev_s  &  def_s),  'rgba(34,197,94,0.3)')
    link('Preventive', 'Immediate', avg(prev_s  & ~def_s),  'rgba(245,158,11,0.3)')
    link('Reactive',   'Immediate', avg(~prev_s & ~def_s),  'rgba(239,68,68,0.3)')
    link('Reactive',   'Deferred',  avg(~prev_s &  def_s),  'rgba(148,163,184,0.3)')

    ct_map = {
        'deferred_batch': ('Deferred Batch', 'rgba(59,130,246,0.3)'),
        'emergency':      ('Emergency',       'rgba(239,68,68,0.3)'),
        'immediate':      ('Urgent',          'rgba(245,158,11,0.3)'),
        'end_of_life':    ('End of Life',     'rgba(148,163,184,0.3)'),
    }
    for ct_key, (ct_node, ct_color) in ct_map.items():
        cm = ct_s == ct_key
        link('Deferred',  ct_node, avg(def_s  & cm), ct_color)
        link('Immediate', ct_node, avg(~def_s & cm), ct_color)

    it_map = {
        'full_workover':        'Full Workover',
        'light_intervention':   'Light Intervention',
        'rigless_intervention': 'Rigless Intervention',
    }
    for ct_key, (ct_node, _) in ct_map.items():
        cm = ct_s == ct_key
        for it_key, it_node in it_map.items():
            link(ct_node, it_node, avg(cm & (it_s == it_key)), 'rgba(139,92,246,0.3)')

    node_colors = [
        '#475569',  # All Events
        '#22c55e',  # Detected
        '#ef4444',  # Undetected
        '#22c55e',  # Preventive
        '#f59e0b',  # Reactive
        '#3b82f6',  # Deferred
        '#f59e0b',  # Immediate
        '#3b82f6',  # Deferred Batch
        '#ef4444',  # Emergency
        '#f59e0b',  # Urgent
        '#64748b',  # End of Life
        '#8b5cf6',  # Full Workover
        '#8b5cf6',  # Light Intervention
        '#8b5cf6',  # Rigless Intervention
    ]

    return {
        'labels':      labels,
        'sources':     srcs,
        'targets':     tgts,
        'values':      vals,
        'link_colors': lcolors,
        'node_colors': node_colors,
    }
