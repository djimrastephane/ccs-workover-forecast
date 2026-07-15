"""
Reliability model — MTTF-based with bathtub curve lifecycle phases.

Replaces the old fixed annual-probability approach with:
  1. Per-simulation MTTF sampling from a triangular distribution
  2. Exponential reliability model: P(fail) = 1 - exp(-1/MTTF)
  3. Bathtub curve lifecycle multiplier (infant / useful / wear-out)
"""
import numpy as np


# ── MTTF sampling ─────────────────────────────────────────────────────────────

def sample_mttf(P10: float, P90: float, rng: np.random.Generator, n: int) -> np.ndarray:
    """
    Sample n MTTF values from a triangular distribution.
    P10 = pessimistic (short MTTF, high failure rate)
    P90 = optimistic  (long  MTTF, low  failure rate)
    Mode = midpoint
    Returns shape (n,).
    """
    mid = (P10 + P90) / 2.0
    return rng.triangular(P10, mid, P90, size=n)


def mttf_to_annual_prob(mttf: np.ndarray) -> np.ndarray:
    """Exponential reliability: P_fail = 1 - exp(-1 / MTTF). Shape unchanged."""
    return 1.0 - np.exp(-1.0 / np.maximum(mttf, 0.1))


# ── Bathtub curve ─────────────────────────────────────────────────────────────

LIFECYCLE_SHAPES = ('bathtub', 'infant', 'plateau', 'wear_out')


def lifecycle_multiplier_vector(
    operating_years: int, start_age: int = 0, shape: str = 'bathtub'
) -> np.ndarray:
    """
    Return shape (operating_years,) of lifecycle multipliers.

    'bathtub' (default — mechanical/well-age-driven degradation):
      Phase 1 — Infant mortality (years 1-2): 1.5×
        Installation damage, faulty gauges, poor packer setting.
      Phase 2 — Useful life (years 3 to 70% of life): 1.0×
        Random, uncorrelated failures.
      Phase 3 — Wear-out (final 30% of life): increasing from 1.0× to 1.8×
        Corrosion, fatigue, elastomer degradation.
        Linear ramp avoids a cliff at end of life; models gradual degradation.
      start_age offsets the well's position on the curve: a converted legacy
      well with start_age=20 evaluates effective years 21..20+N instead of
      1..N, so it skips infant mortality and enters the wear-out ramp early.
      Phase boundaries stay anchored to the field design life; effective
      years beyond design life hold at the 1.8× wear-out ceiling.

    Injection-driven shapes (geochemical flow-assurance sub-modes; DOE/NETL-
    2020/2634 Exhibit 3-1). These mechanisms begin at CO₂ injection start,
    not well construction, so start_age is intentionally ignored — a
    converted legacy well has the same hydrate/halite/scaling exposure clock
    as a new well:
      'infant'   — hydrate formation: 2.0× at startup (year 1), declining
                   linearly to 1.0× by year 5, flat thereafter.
      'plateau'  — halite precipitation: ramps 0.8× → 1.2× over the first
                   40% of field life as near-wellbore dry-out accumulates,
                   then holds at the plateau.
      'wear_out' — carbonate scaling / microbial plugging: 1.0× useful life,
                   then the standard wear-out ramp to 1.8× (no infant phase).
    """
    if shape not in LIFECYCLE_SHAPES:
        raise ValueError(f'Unknown lifecycle shape: {shape!r} (expected one of {LIFECYCLE_SHAPES})')

    wear_start = max(3, int(operating_years * 0.70))
    mult = np.ones(operating_years)

    if shape == 'infant':
        for yr in range(operating_years):
            year = yr + 1  # injection year — start_age does not apply
            mult[yr] = 2.0 - 0.25 * (year - 1) if year < 5 else 1.0
        return mult

    if shape == 'plateau':
        ramp_end = max(2, int(operating_years * 0.40))
        for yr in range(operating_years):
            year = yr + 1  # injection year — start_age does not apply
            frac = min((year - 1) / max(ramp_end - 1, 1), 1.0)
            mult[yr] = 0.8 + frac * 0.4
        return mult

    if shape == 'wear_out':
        for yr in range(operating_years):
            year = yr + 1  # injection year — start_age does not apply
            if year >= wear_start:
                frac = (year - wear_start) / max(operating_years - wear_start, 1)
                mult[yr] = 1.0 + min(frac, 1.0) * 0.8
        return mult

    # 'bathtub'
    for yr in range(operating_years):
        year = yr + 1 + start_age  # effective age on the bathtub curve, 1-based
        if year <= 2:
            mult[yr] = 1.5
        elif year < wear_start:
            mult[yr] = 1.0
        else:
            frac = (year - wear_start) / max(operating_years - wear_start, 1)
            mult[yr] = 1.0 + min(frac, 1.0) * 0.8   # linear ramp, capped at 1.8×
    return mult


# ── Cumulative failure probability ────────────────────────────────────────────

def cumulative_failure_probability(
    adj_prob: np.ndarray,
) -> np.ndarray:
    """
    Given annual adjusted probabilities adj_prob of shape (n_sims, n_years),
    return cumulative failure probability using reliability product.

    F(t) = 1 - prod(1 - p(y)) for y in 1..t
    """
    log_survival = np.log(np.maximum(1.0 - adj_prob, 1e-12))
    cum_log_survival = np.cumsum(log_survival, axis=1)
    return 1.0 - np.exp(cum_log_survival)


def threshold_year(cum_fail_prob: np.ndarray, threshold: float) -> np.ndarray:
    """
    Return shape (n_sims,) — first year (1-based) where cumulative failure
    probability >= threshold, or operating_years+1 if never reached.
    """
    n_sims, n_years = cum_fail_prob.shape
    exceeds = cum_fail_prob >= threshold
    has_any = exceeds.any(axis=1)
    first = np.where(has_any, np.argmax(exceeds, axis=1) + 1, n_years + 1)
    return first
