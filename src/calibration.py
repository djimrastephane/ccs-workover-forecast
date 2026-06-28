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
) -> pd.DataFrame:
    """
    Proxy tornado chart.
    Uncertainty contribution ∝ cost share × normalised MTTF spread.
    MTTF spread = (P90 − P10) / P10.
    """
    if contributions.empty or component_assumptions.empty:
        return pd.DataFrame()

    rows = []
    for _, comp in component_assumptions.iterrows():
        comp_id = comp['component']
        p10, p90 = float(comp['P10_MTTF']), float(comp['P90_MTTF'])
        spread = (p90 - p10) / max(p10, 1.0)

        cont = contributions[contributions['component'] == comp_id]
        if cont.empty:
            continue
        cost_pct = float(cont.iloc[0]['cost_pct'])
        cost_m = float(cont.iloc[0]['cost_m'])

        unc_m = cost_m * spread / (1.0 + spread)
        rows.append({
            'component': comp_id,
            'display_name': comp['display_name'],
            'barrier_class': comp['barrier_class'],
            'cost_pct': cost_pct,
            'mttf_p10': p10,
            'mttf_p90': p90,
            'mttf_spread': round(spread, 3),
            'cost_m': round(cost_m, 1),
            'uncertainty_m': round(unc_m, 1),
            'low_estimate': round(cost_m * (1 - spread / (1 + spread)), 1),
            'high_estimate': round(cost_m * (1 + spread / (1 + spread)), 1),
        })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    total_unc = df['uncertainty_m'].sum()
    df['uncertainty_pct'] = (df['uncertainty_m'] / max(total_unc, 1.0) * 100).round(1)
    return df.sort_values('uncertainty_pct', ascending=False).reset_index(drop=True)
