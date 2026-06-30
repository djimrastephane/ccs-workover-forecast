"""
Co-location discount for interventions on the same well in the same year.

When multiple components fail on the same well in the same year a single
well visit can address all of them. The most expensive intervention is
charged in full (primary); every additional component on that well in that
year is charged discount_factor × standalone cost (default 0.25).

This corrects the independent-pricing assumption in failure_generator, which
overstates lifecycle cost when multiple components fail on the same well
in the same year.
"""
import pandas as pd


def apply_co_location_discount(
    failure_df: pd.DataFrame,
    discount_factor: float = 0.25,
) -> pd.DataFrame:
    """
    Apply co-location discount to secondary interventions per (sim, year, well).

    For each group with > 1 event:
      - Highest-cost event: full price (primary)
      - All others: estimated_cost × discount_factor

    Adds boolean column 'co_location_discount_applied'.
    Returns a copy; does not modify the input.
    """
    if failure_df.empty or discount_factor >= 1.0:
        df = failure_df.copy()
        df['co_location_discount_applied'] = False
        return df

    df = failure_df.copy()

    # Rank within (sim, year, well) by cost descending; rank 1 = primary
    df['_rank'] = (
        df.groupby(['simulation_id', 'year', 'well_id'])['estimated_cost']
        .rank(method='first', ascending=False)
    )
    secondary = df['_rank'] > 1
    df.loc[secondary, 'estimated_cost'] = (
        df.loc[secondary, 'estimated_cost'] * discount_factor
    )
    df['co_location_discount_applied'] = secondary
    df.drop(columns=['_rank'], inplace=True)

    return df
