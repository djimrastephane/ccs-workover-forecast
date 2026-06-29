"""Calibration scoring and uncertainty decomposition."""
import pandas as pd
import numpy as np

_SOURCE_SCORES = {
    'oreda': 1.00,
    'literature': 0.80,
    'spe_paper': 0.75,
    'operator_analogue': 0.65,
    'expert_judgement': 0.40,
    'synthetic_assumption': 0.10,
}
_CONFIDENCE_MULT = {'high': 1.00, 'medium': 0.75, 'low': 0.50}
_SENSITIVITY_WEIGHT = {'high': 1.00, 'medium': 0.60, 'low': 0.30}


def compute_calibration_score(assumption_quality: pd.DataFrame) -> dict:
    if assumption_quality.empty:
        return {
            'score': 0, 'level': 'Unknown', 'color': 'red',
            'breakdown': {}, 'critical_gaps': [], 'n_assumptions': 0,
        }

    total_weight = 0.0
    weighted_score = 0.0
    critical_gaps = []

    for _, row in assumption_quality.iterrows():
        source = str(row.get('source_type', 'synthetic_assumption')).lower().strip()
        confidence = str(row.get('confidence_level', 'low')).lower().strip()
        # 'high impact' → 'high', 'medium impact' → 'medium', etc.
        sensitivity = str(row.get('sensitivity_level', 'medium')).lower().strip().split()[0]

        src_score = _SOURCE_SCORES.get(source, 0.10)
        conf_mult = _CONFIDENCE_MULT.get(confidence, 0.50)
        sens_weight = _SENSITIVITY_WEIGHT.get(sensitivity, 0.60)

        weighted_score += src_score * conf_mult * sens_weight
        total_weight += sens_weight

        if sensitivity == 'high' and (src_score < 0.50 or confidence == 'low'):
            critical_gaps.append({
                'parameter': str(row.get('parameter', '?')),
                'component': str(row.get('component', '?')),
                'source': source,
                'confidence': confidence,
                'sensitivity': str(row.get('sensitivity_level', '?')),
                'notes': str(row.get('notes', '')),
            })

    score = round(min(max(weighted_score / max(total_weight, 1.0) * 100, 0), 100), 1)

    if score >= 70:
        level, color = 'Good calibration quality', 'green'
    elif score >= 50:
        level, color = 'Moderate calibration quality', 'amber'
    elif score >= 30:
        level, color = 'Low calibration quality', 'red'
    else:
        level, color = 'High uncertainty — treat outputs with caution', 'red'

    breakdown = {}
    for src in _SOURCE_SCORES:
        n = int((assumption_quality['source_type'].str.lower().str.strip() == src).sum())
        if n > 0:
            breakdown[src] = n

    return {
        'score': score, 'level': level, 'color': color,
        'breakdown': breakdown, 'critical_gaps': critical_gaps,
        'n_assumptions': len(assumption_quality),
    }


def compute_uncertainty_decomposition(
    contributions: pd.DataFrame,
    component_assumptions: pd.DataFrame,
    n_simulations: int = 500,
) -> pd.DataFrame:
    """
    Analytical OAT (one-at-a-time) sensitivity tornado.

    For each component, vary its MTTF from P10 (pessimistic) to P90 (optimistic)
    while holding everything else at mode = (P10+P90)/2. Estimate the resulting
    change in lifecycle cost using the ratio of annual failure probabilities:

        ΔCost = base_cost_per_sim × (prob_variant / prob_base − 1)

    where prob = 1 − exp(−1/MTTF).

    Returns one row per component with delta_low ($M pessimistic, positive),
    delta_high ($M optimistic, negative), and swing = delta_low − delta_high.
    Sorted by swing descending so the widest bar is at the top.
    """
    import numpy as np

    if contributions.empty or component_assumptions.empty:
        return pd.DataFrame()

    rows = []
    for _, comp in component_assumptions.iterrows():
        comp_id = comp['component']
        p10, p90 = float(comp['P10_MTTF']), float(comp['P90_MTTF'])
        mode = (p10 + p90) / 2.0

        cont = contributions[contributions['component'] == comp_id]
        if cont.empty:
            continue

        # Per-simulation baseline cost for this component
        cost_m_total = float(cont.iloc[0]['cost_m'])
        cost_m = cost_m_total / max(n_simulations, 1)
        cost_pct = float(cont.iloc[0]['cost_pct'])

        # Annual failure probabilities under each MTTF scenario
        prob_base = 1.0 - np.exp(-1.0 / max(mode, 0.1))
        prob_low  = 1.0 - np.exp(-1.0 / max(p10,  0.1))   # more failures
        prob_high = 1.0 - np.exp(-1.0 / max(p90,  0.1))   # fewer failures

        if prob_base < 1e-9:
            continue

        # Cost change relative to base: positive = more expensive, negative = cheaper
        delta_low  = cost_m * (prob_low  / prob_base - 1.0)   # P10 MTTF → higher cost
        delta_high = cost_m * (prob_high / prob_base - 1.0)   # P90 MTTF → lower cost
        swing = delta_low - delta_high

        rows.append({
            'component':    comp_id,
            'display_name': comp['display_name'],
            'barrier_class': comp['barrier_class'],
            'cost_pct':     round(cost_pct, 1),
            'cost_m':       round(cost_m, 2),
            'mttf_p10':     p10,
            'mttf_p90':     p90,
            'mttf_mode':    round(mode, 1),
            'prob_base':    round(prob_base * 100, 3),
            'delta_low':    round(delta_low,  2),   # $ M, pessimistic (P10 MTTF)
            'delta_high':   round(delta_high, 2),   # $ M, optimistic  (P90 MTTF)
            'swing':        round(swing, 2),
        })

    if not rows:
        return pd.DataFrame()

    return (
        pd.DataFrame(rows)
        .sort_values('swing', ascending=False)
        .reset_index(drop=True)
    )
