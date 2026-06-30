"""
Field calibration engine.

Compares observed field failure events against the model's expected failure
rates to derive component-level calibration factors.  These factors adjust
MTTF assumptions before simulation, making the model progressively more
accurate as the field matures.

Hierarchy:
  Global MTTF assumptions (literature / expert judgement)
       ↓
  Field calibration factor  (observed field evidence)
       ↓
  Effective MTTF used in this simulation run

Formula:
  expected_failures  = Σ base_rate × bathtub_mult(t)  [summed over all well-years]
  calibration_factor = observed_failures / expected_failures
  confidence         = min(n_observed / 20, 1.0)
  effective_factor   = 1 + confidence × (calibration_factor − 1)
  calibrated_MTTF    = base_MTTF / effective_factor

Bathtub weighting (via lifecycle_multiplier_vector) ensures the expected count
reflects the actual lifecycle phase mix in the observation window, so the
calibration factor corrects only for MTTF assumption error — not for infant
mortality or wear-out effects that the simulation already models explicitly.

The confidence-weighted effective_factor prevents a single observed event
from rewriting the entire assumption set.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path

from .reliability_model import lifecycle_multiplier_vector

_OBS_PATH = Path(__file__).parent.parent / 'data' / 'observations' / 'observed_events.csv'
_CAL_DIR  = Path(__file__).parent.parent / 'data' / 'calibration'

_CALIBRABLE_EVENTS = {'failure', 'degradation'}


# ── I/O ──────────────────────────────────────────────────────────────────────

def load_observed_events(path: Path = _OBS_PATH) -> pd.DataFrame:
    """Load observed field events.  Returns empty DataFrame if file absent."""
    try:
        return pd.read_csv(path)
    except FileNotFoundError:
        return pd.DataFrame()


def list_fields(observed_events: pd.DataFrame) -> list[str]:
    if observed_events.empty or 'field_id' not in observed_events.columns:
        return []
    return sorted(observed_events['field_id'].dropna().unique().tolist())


# ── Core calibration ──────────────────────────────────────────────────────────

def compute_calibration_factors(
    observed_events: pd.DataFrame,
    component_assumptions: pd.DataFrame,
    field_id: str | None = None,
    field_design_life: int = 30,
) -> pd.DataFrame:
    """
    Compute per-component calibration factors for a given field.

    Expected failures  = Σ base_rate × bathtub_mult(t)  [over all observed well-years]
    Calibration factor = observed_failures / expected_failures
    Confidence         = min(observed_failures / 20, 1.0)
    Effective factor   = 1 + confidence × (calibration_factor − 1)

    bathtub_mult(t) uses lifecycle_multiplier_vector(field_design_life) so that the
    expected count reflects the actual lifecycle phase mix of the observation window.
    The calibration factor therefore corrects only for MTTF assumption error, not for
    infant-mortality or wear-out effects the simulation already applies.

    Returns one row per component in component_assumptions.
    """
    if observed_events.empty:
        return pd.DataFrame()

    obs = observed_events.copy()
    if field_id:
        obs = obs[obs['field_id'] == field_id]
    if obs.empty:
        return pd.DataFrame()

    # Fleet exposure: one row per well with its observation window
    well_info = obs.groupby('well_id').agg(
        install_year=('install_year', 'min'),
        last_event_year=('event_year', 'max'),
    )
    well_info['well_years'] = well_info['last_event_year'] - well_info['install_year'] + 1
    n_wells_observed = len(well_info)
    total_well_years = float(well_info['well_years'].sum())

    # Bathtub-weighted exposure: Σ bathtub_mult(t) across all observed well-years.
    # This is component-agnostic — multiply by base_rate per component below.
    lc = lifecycle_multiplier_vector(field_design_life)
    bathtub_exposure = 0.0
    for _, well in well_info.iterrows():
        n_yrs = int(well['well_years'])
        idxs  = np.arange(n_yrs)
        # Clamp to design life; beyond it, use the final wear-out multiplier
        mults = np.where(idxs < len(lc), lc[np.minimum(idxs, len(lc) - 1)], lc[-1])
        bathtub_exposure += float(mults.sum())

    # Observed failure/degradation counts per component
    fail_mask = obs['event_type'].isin(_CALIBRABLE_EVENTS)
    obs_counts = (
        obs[fail_mask]
        .groupby('component')
        .size()
        .to_dict()
    )

    rows: list[dict] = []
    for _, comp_row in component_assumptions.iterrows():
        comp      = comp_row['component']
        display   = comp_row['display_name']
        P10       = float(comp_row['P10_MTTF'])
        P90       = float(comp_row['P90_MTTF'])
        mode_mttf = (P10 + P90) / 2.0

        base_rate         = 1.0 - np.exp(-1.0 / mode_mttf)
        expected_failures = base_rate * bathtub_exposure

        n_obs = obs_counts.get(comp, 0)

        calibration_factor = (n_obs / expected_failures) if (n_obs > 0 and expected_failures > 0) else None

        confidence       = min(n_obs / 20.0, 1.0)
        effective_factor = (
            1.0 + confidence * (calibration_factor - 1.0)
            if calibration_factor is not None else 1.0
        )
        recommended_mttf = mode_mttf / effective_factor

        rows.append({
            'field_id':            field_id or 'all',
            'component':           comp,
            'display_name':        display,
            'mode_mttf':           round(mode_mttf, 1),
            'expected_failures':   round(expected_failures, 2),
            'observed_failures':   n_obs,
            'calibration_factor':  round(calibration_factor, 3) if calibration_factor is not None else None,
            'confidence':          round(confidence, 3),
            'effective_factor':    round(effective_factor, 3),
            'recommended_mttf':    round(recommended_mttf, 1),
            'n_wells_observed':    n_wells_observed,
            'total_well_years':    round(total_well_years, 1),
            'bathtub_exposure':    round(bathtub_exposure, 1),
        })

    return pd.DataFrame(rows)


def apply_field_calibration(
    component_assumptions: pd.DataFrame,
    calibration_factors: pd.DataFrame,
) -> pd.DataFrame:
    """
    Apply calibration effective_factors to component P10/P90 MTTF.

    new_MTTF = old_MTTF / effective_factor

    Returns a copy of component_assumptions with adjusted MTTF values.
    Components with effective_factor == 1.0 are unchanged.
    """
    if calibration_factors.empty:
        return component_assumptions

    df = component_assumptions.copy()
    df['P10_MTTF'] = df['P10_MTTF'].astype(float)
    df['P90_MTTF'] = df['P90_MTTF'].astype(float)

    eff_map = dict(
        zip(calibration_factors['component'], calibration_factors['effective_factor'])
    )
    for comp, eff in eff_map.items():
        if eff == 1.0:
            continue
        mask = df['component'] == comp
        if mask.any():
            df.loc[mask, 'P10_MTTF'] = (df.loc[mask, 'P10_MTTF'] / eff).round(1)
            df.loc[mask, 'P90_MTTF'] = (df.loc[mask, 'P90_MTTF'] / eff).round(1)

    return df


def save_calibration_factors(
    cal_df: pd.DataFrame,
    field_id: str,
) -> Path:
    """Persist calibration factors to data/calibration/<field_id>_calibration.csv."""
    _CAL_DIR.mkdir(parents=True, exist_ok=True)
    out = _CAL_DIR / f'{field_id}_calibration.csv'
    cal_df.to_csv(out, index=False)
    return out


# ── Maturity score ────────────────────────────────────────────────────────────

def compute_maturity_score(
    observed_events: pd.DataFrame,
    calibration_factors: pd.DataFrame,
    field_id: str | None = None,
    n_total_components: int = 15,
) -> dict:
    """
    Compute Reliability Maturity Score (0–100) for a field.

    Factors:
      30% — years of operational history  (max at 15 yrs)
      30% — number of observed events     (max at 50 events)
      20% — component coverage            (fraction of components with data)
      20% — mean calibration confidence
    """
    if observed_events.empty:
        return {'score': 0.0, 'level': 'No data', 'color': 'red', 'breakdown': {}}

    obs = observed_events.copy()
    if field_id:
        obs = obs[obs['field_id'] == field_id]
    if obs.empty:
        return {'score': 0.0, 'level': 'No data', 'color': 'red', 'breakdown': {}}

    years_history = max(obs['event_year'].max() - obs['install_year'].min(), 0)
    n_events      = len(obs[obs['event_type'].isin(_CALIBRABLE_EVENTS)])
    n_comps_with  = obs[obs['event_type'].isin(_CALIBRABLE_EVENTS)]['component'].nunique()

    years_score    = min(years_history / 15.0, 1.0)
    events_score   = min(n_events / 50.0, 1.0)
    coverage_score = n_comps_with / n_total_components

    mean_conf = (
        float(calibration_factors['confidence'].mean())
        if not calibration_factors.empty else 0.0
    )

    score = 100.0 * (
        0.30 * years_score
        + 0.30 * events_score
        + 0.20 * coverage_score
        + 0.20 * mean_conf
    )
    score = round(score, 1)

    if score < 20:
        level, color = 'Concept study', 'red'
    elif score < 40:
        level, color = 'Pre-FEED', 'red'
    elif score < 60:
        level, color = 'FEED', 'amber'
    elif score < 80:
        level, color = 'Early operations', 'amber'
    else:
        level, color = 'Mature field', 'green'

    return {
        'score': score,
        'level': level,
        'color': color,
        'breakdown': {
            'years_history':        round(years_history, 1),
            'n_calibrable_events':  n_events,
            'n_components_covered': n_comps_with,
            'mean_confidence':      round(mean_conf, 3),
        },
    }


# ── Drift detection ───────────────────────────────────────────────────────────

def detect_drift(calibration_factors: pd.DataFrame, min_confidence: float = 0.10) -> list[dict]:
    """
    Identify components where observed rates deviate significantly from model.

    Threshold:
      calibration_factor > 1.50  → model underestimates failures (optimistic)
      calibration_factor < 0.50  → model overestimates failures (conservative)

    Only fires when confidence >= min_confidence to suppress noise.
    """
    if calibration_factors.empty:
        return []

    alerts: list[dict] = []
    for _, row in calibration_factors.iterrows():
        cf = row['calibration_factor']
        if cf is None or pd.isna(cf) or row['confidence'] < min_confidence:
            continue

        comp = row['display_name']
        if cf > 1.50:
            pct = (cf - 1) * 100
            alerts.append({
                'component':          comp,
                'severity':           'critical' if cf > 2.0 else 'warning',
                'direction':          'higher_than_expected',
                'calibration_factor': cf,
                'message': (
                    f'**{comp}** failures exceed forecast by {pct:.0f}%. '
                    f'Model assumptions are optimistic — consider reducing P50 MTTF. '
                    f'({row["observed_failures"]:.0f} observed vs '
                    f'{row["expected_failures"]:.1f} expected)'
                ),
            })
        elif cf < 0.50:
            pct = (1 - cf) * 100
            alerts.append({
                'component':          comp,
                'severity':           'info',
                'direction':          'lower_than_expected',
                'calibration_factor': cf,
                'message': (
                    f'**{comp}** failures are {pct:.0f}% below forecast. '
                    f'Model assumptions may be conservative. '
                    f'({row["observed_failures"]:.0f} observed vs '
                    f'{row["expected_failures"]:.1f} expected)'
                ),
            })

    return sorted(alerts, key=lambda x: abs(x['calibration_factor'] - 1.0), reverse=True)
