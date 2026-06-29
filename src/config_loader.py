import os
import pandas as pd

_DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'assumptions')


def _path(filename):
    return os.path.join(_DATA_DIR, filename)


def _parse_bools(df, columns):
    for col in columns:
        if col in df.columns:
            df[col] = df[col].map(
                {'true': True, 'false': False, True: True, False: False}
            )
    return df


def load_component_assumptions() -> pd.DataFrame:
    """Load MTTF-based component reliability assumptions."""
    df = pd.read_csv(_path('component_failure_assumptions.csv'))
    return _parse_bools(df, ['can_defer', 'safety_critical', 'injector_only', 'trsv_only'])


def load_cost_assumptions(scenario: str = 'base_case') -> dict:
    df = pd.read_csv(_path('cost_assumptions.csv'))
    filtered = df[df['scenario'] == scenario]
    if filtered.empty:
        filtered = df[df['scenario'] == 'base_case']
    return filtered.set_index('cost_item')['value_usd'].to_dict()


def load_scenario_config() -> pd.DataFrame:
    df = pd.read_csv(_path('scenario_config.csv'))
    return _parse_bools(df, ['offshore', 'scssv_enabled']).set_index('scenario_id')


# Kept for backward-compat with any code that still imports it
def load_intervention_rules() -> pd.DataFrame:
    try:
        return pd.read_csv(_path('intervention_rules.csv'))
    except FileNotFoundError:
        return pd.DataFrame()


def load_assumption_quality() -> pd.DataFrame:
    """Load assumption quality register metadata."""
    try:
        return pd.read_csv(_path('assumption_quality.csv'))
    except FileNotFoundError:
        return pd.DataFrame()


def load_monitoring_config() -> pd.DataFrame:
    """Load per-tier detection probability overrides (minimal / standard / comprehensive)."""
    try:
        return pd.read_csv(_path('monitoring_config.csv'))
    except FileNotFoundError:
        return pd.DataFrame()
