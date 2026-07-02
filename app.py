import datetime
import streamlit as st
import pandas as pd
import plotly.express as px

from src.simulation import run_simulation
from src.config_loader import (
    load_component_assumptions, load_intervention_rules,
    load_cost_assumptions, load_scenario_config,
    load_assumption_quality,
)
from src.qa import compute_qa_metrics, generate_qa_warnings
from src.explainability import (
    explain_cost_driver, explain_peak_demand,
    explain_campaign_count, explain_highest_risk,
)
from src.calibration import compute_calibration_score, compute_uncertainty_decomposition
from src.field_calibration import (
    load_observed_events, list_fields,
    compute_calibration_factors, compute_maturity_score, detect_drift,
)
from src.reporting import (
    build_annual_forecast, build_component_summary, build_scenario_comparison,
    get_highest_risk_component, format_cost,
    compute_asset_health_scores, generate_executive_narrative,
    compute_component_contributions, compute_heatmap_data,
)
from src.plotting import (
    plot_workover_fan_chart, plot_cost_fan_chart,
    plot_risk_matrix, plot_bathtub_curve, plot_lifecycle_heatmap,
    plot_annual_workover_demand, plot_annual_intervention_demand,
    plot_cumulative_workovers, plot_lifecycle_cost_distribution,
    plot_failure_by_component, plot_intervention_type_split,
    plot_severity_distribution, plot_cost_by_component,
    plot_component_treemap, plot_cost_waterfall,
    plot_campaign_gantt, plot_campaign_cost_by_year, plot_campaign_timeline, plot_campaign_size_distribution,
    plot_deferred_queue_evolution, plot_deferred_queue, plot_immediate_vs_deferred,
    plot_scenario_comparison, plot_scenario_workovers,
    plot_tornado_chart,
)
from src.trace import build_simulation_trace, compute_worst_year_breakdown
from src.story import (
    build_well_journey, build_event_story_card, build_decision_path,
    build_campaign_story, build_sankey_data,
    BARRIER_ICON, BARRIER_COLOR, TRIGGER_ICON, CAMPAIGN_ICON,
)

# ── Page config (must be first) ───────────────────────────────────────────────
st.set_page_config(
    page_title='CCS Workover Forecast',
    layout='wide',
    initial_sidebar_state='expanded',
)

# ── Global CSS injection ──────────────────────────────────────────────────────
st.markdown("""
<style>
/* Hide default Streamlit chrome */
#MainMenu, footer, header { visibility: hidden; }

/* Sidebar */
[data-testid="stSidebar"] {
    border-right: 1px solid #1e293b;
    padding-top: 0.5rem;
}
[data-testid="stSidebar"] > div:first-child { padding-top: 1rem; }

/* Tab bar */
.stTabs [data-baseweb="tab-list"] {
    background: #111827;
    border-radius: 6px;
    padding: 3px;
    gap: 2px;
    border: 1px solid #1e293b;
}
.stTabs [data-baseweb="tab"] {
    background: transparent;
    color: #64748b;
    border-radius: 4px;
    font-size: 0.78rem;
    font-weight: 500;
    padding: 5px 14px;
    letter-spacing: 0.01em;
}
.stTabs [aria-selected="true"] {
    background: #1e293b !important;
    color: #e2e8f0 !important;
}
.stTabs [data-baseweb="tab-panel"] { padding-top: 1.25rem; }

/* Native metric override */
[data-testid="stMetric"] {
    background: #111827;
    border: 1px solid #1e293b;
    border-radius: 6px;
    padding: 0.9rem 1.1rem;
}
[data-testid="stMetricLabel"] p {
    font-size: 0.65rem !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.08em !important;
    color: #64748b !important;
}
[data-testid="stMetricValue"] {
    font-size: 1.65rem !important;
    font-weight: 700 !important;
    color: #f1f5f9 !important;
}
[data-testid="stMetricDelta"] { font-size: 0.72rem !important; }

/* Dividers */
hr { border-color: #1e293b; margin: 1rem 0; }

/* Expander */
details { border: 1px solid #1e293b !important; border-radius: 6px !important; }
summary { color: #94a3b8 !important; font-size: 0.8rem !important; }

/* Dataframe */
[data-testid="stDataFrame"] { border: 1px solid #1e293b; border-radius: 6px; }

/* Sidebar section headers */
.sb-section {
    font-size: 0.58rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    color: #475569;
    padding: 0.65rem 0 0.25rem;
    border-bottom: 1px solid #1e293b;
    margin-bottom: 0.6rem;
}

/* Page section label */
.section-label {
    font-size: 0.58rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    color: #475569;
    padding-bottom: 0.4rem;
    border-bottom: 1px solid #1e293b;
    margin: 1.25rem 0 0.85rem;
}
</style>
""", unsafe_allow_html=True)

# ── HTML component helpers ────────────────────────────────────────────────────
_BORDER = {
    'red':    '#ef4444',
    'amber':  '#f59e0b',
    'green':  '#10b981',
    'blue':   '#3b82f6',
    'purple': '#8b5cf6',
}


def kpi_card(title: str, value: str, subtitle: str, color: str = 'blue') -> str:
    bc = _BORDER.get(color, _BORDER['blue'])
    return f"""
    <div style="background:#111827;border:1px solid #1e293b;border-left:4px solid {bc};
                border-radius:0 8px 8px 0;padding:1rem 1.2rem;height:100%;box-sizing:border-box;">
      <div style="font-size:.6rem;font-weight:700;text-transform:uppercase;letter-spacing:.1em;
                  color:#64748b;margin-bottom:.45rem;">{title}</div>
      <div style="font-size:1.8rem;font-weight:700;color:#f1f5f9;line-height:1.05;
                  margin-bottom:.3rem;">{value}</div>
      <div style="font-size:.68rem;font-weight:500;color:{bc};">{subtitle}</div>
    </div>"""


def health_row(label: str, score: float, status: str, description: str) -> str:
    color = '#10b981' if score >= 75 else '#f59e0b' if score >= 50 else '#ef4444'
    pct = f'{score:.0f}%'
    return f"""
    <div style="margin-bottom:.85rem;">
      <div style="display:flex;justify-content:space-between;margin-bottom:.22rem;">
        <span style="color:#cbd5e1;font-size:.78rem;font-weight:500;">{label}</span>
        <span style="color:{color};font-size:.72rem;font-weight:600;">{score:.0f} — {status}</span>
      </div>
      <div style="background:#1e293b;border-radius:3px;height:7px;overflow:hidden;">
        <div style="background:{color};width:{pct};height:100%;border-radius:3px;"></div>
      </div>
      <p style="color:#475569;font-size:.64rem;margin:.18rem 0 0;">{description}</p>
    </div>"""


def narrative_card(text: str) -> str:
    import re
    # Convert **bold** to <b>
    text = re.sub(r'\*\*(.+?)\*\*', r'<b style="color:#e2e8f0;">\1</b>', text)
    return f"""
    <div style="background:#0f172a;border-left:3px solid #3b82f6;border-radius:0 6px 6px 0;
                padding:.85rem 1.1rem;margin-bottom:.6rem;">
      <p style="color:#94a3b8;font-size:.83rem;margin:0;line-height:1.65;">{text}</p>
    </div>"""


def section(label: str) -> None:
    st.markdown(f'<div class="section-label">{label}</div>', unsafe_allow_html=True)


def scenario_card(name: str, summary: dict, highlight: str = '') -> str:
    border = '#10b981' if highlight == 'best' else '#ef4444' if highlight == 'worst' else '#1e293b'
    top_border = border
    badge = (' <span style="font-size:.6rem;background:#064e3b;color:#10b981;'
             'padding:.1rem .4rem;border-radius:3px;">BEST</span>' if highlight == 'best'
             else ' <span style="font-size:.6rem;background:#7f1d1d;color:#ef4444;'
             'padding:.1rem .4rem;border-radius:3px;">HIGHEST COST</span>'
             if highlight == 'worst' else '')
    p50c = format_cost(summary.get('p50_lifecycle_cost', 0))
    p90c = format_cost(summary.get('p90_lifecycle_cost', 0))
    p50w = f"{summary.get('p50_workovers', 0):.0f}"
    p90w = f"{summary.get('p90_workovers', 0):.0f}"
    peak = f"{summary.get('p50_peak_annual_demand', 0):.0f}"
    camps = f"{summary.get('p50_campaigns', 0):.0f}"
    return f"""
    <div style="background:#111827;border:1px solid {border};border-top:3px solid {top_border};
                border-radius:0 0 8px 8px;padding:1rem;height:100%;box-sizing:border-box;">
      <div style="font-size:.7rem;font-weight:700;color:#e2e8f0;margin-bottom:.6rem;">{name}{badge}</div>
      <div style="font-size:1.5rem;font-weight:700;color:#f1f5f9;">{p50c}</div>
      <div style="font-size:.62rem;color:#475569;margin-bottom:.75rem;">P50 Lifecycle Cost</div>
      <div style="font-size:.75rem;color:#94a3b8;line-height:1.8;">
        <span style="color:#e2e8f0;">{p50w}</span> workovers (P50) &nbsp;|&nbsp;
        <span style="color:#ef4444;">{p90w}</span> (P90)<br>
        <span style="color:#e2e8f0;">{peak}</span> peak interventions / yr<br>
        <span style="color:#e2e8f0;">{camps}</span> planned campaigns &nbsp;·&nbsp;
        <span style="color:#94a3b8;">P90 cost {p90c}</span>
      </div>
    </div>"""


# ── Scenario labels ───────────────────────────────────────────────────────────
_SCENARIO_LABELS = {
    'base_case':           'Base Case',
    'conservative_design': 'Conservative Design',
    'low_cost_design':     'Low-Cost Design',
    'high_corrosion':      'High Corrosion',
    'offshore_high_cost':  'Offshore High-Cost',
    'legacy_conversion':   'Legacy Well Conversion',
}

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('### CCS Workover Forecast')
    st.caption('Asset Integrity & Intervention Planning')
    st.divider()

    st.markdown('<div class="sb-section">👤 View Mode</div>', unsafe_allow_html=True)
    view_mode = st.radio(
        'View Mode',
        options=['Executive', 'Engineering', 'Reviewer', 'Developer'],
        index=1,
        label_visibility='collapsed',
        horizontal=True,
        help=(
            'Executive: KPI summary and scenario comparison — for managers and regulators.\n\n'
            'Engineering: Full analysis including risk, campaigns, well journeys, and assumptions — for well integrity and intervention engineers.\n\n'
            'Reviewer: Assumptions, calibration, QA, and full audit trail — for technical reviewers who need to challenge every model decision.\n\n'
            'Developer: All engineering content plus model internals, calibration metrics, and raw distributions — for model validators and reliability engineers.'
        ),
    )

    st.markdown('<div class="sb-section">🏗 Asset Configuration</div>', unsafe_allow_html=True)
    n_wells = st.slider('Total Wells', 10, 500, 100, step=10)
    injector_pct = st.slider('Injectors (%)', 50, 95, 80, step=5)
    n_injectors = int(n_wells * injector_pct / 100)
    n_monitoring = n_wells - n_injectors
    st.caption(f'{n_injectors} injectors · {n_monitoring} monitoring wells')
    operating_years = st.slider('Operating Life (years)', 10, 40, 30, step=5)
    first_injection_year = st.number_input(
        'Simulation Start Year',
        min_value=2020, max_value=2100,
        value=datetime.date.today().year,
        step=1,
        help=(
            'First calendar year of field operations. '
            'Converts field-life years to calendar years for reporting. '
            'Does not affect reliability or ageing calculations.'
        ),
    )

    st.markdown('<div class="sb-section">⚙️ Simulation</div>', unsafe_allow_html=True)
    scenario_id = st.selectbox(
        'Scenario',
        options=list(_SCENARIO_LABELS.keys()),
        format_func=lambda x: _SCENARIO_LABELS[x],
    )
    n_simulations = st.select_slider(
        'Monte Carlo Runs', options=[100, 250, 500, 1000, 2000, 5000, 10000], value=500,
    )

    st.markdown('<div class="sb-section">🔬 Intervention Threshold</div>', unsafe_allow_html=True)
    threshold_pct = st.select_slider(
        'Intervention Probability Threshold',
        options=[70, 75, 80, 85, 90, 95],
        value=90,
        help='Trigger preventive intervention when cumulative failure probability exceeds this level',
    )
    intervention_threshold = threshold_pct / 100.0
    st.caption(f'Current threshold: **{threshold_pct}%** cumulative failure probability')

    if view_mode != 'Executive':
        st.markdown('<div class="sb-section">🎛 Model Mode</div>', unsafe_allow_html=True)
        model_mode = st.radio(
            'Model Mode',
            options=['Intervention Planning', 'Reliability Forecast'],
            label_visibility='collapsed',
            help=(
                'Intervention Planning: full batching and deferred queue logic. '
                'Reliability Forecast: pure component reliability view without scheduling constraints.'
            ),
        )
    else:
        model_mode = 'Intervention Planning'

    st.markdown('<div class="sb-section">📡 Monitoring Program</div>', unsafe_allow_html=True)
    _MON_LABELS = {
        'minimal':       'Minimal',
        'standard':      'Standard',
        'comprehensive': 'Comprehensive',
    }
    monitoring_program = st.radio(
        'Monitoring Configuration',
        options=list(_MON_LABELS.keys()),
        format_func=_MON_LABELS.__getitem__,
        index=1,
        label_visibility='collapsed',
        help=(
            'Controls detection probability for each component.\n\n'
            'Minimal — downhole P/T gauges + occasional wireline surveys only.\n'
            'Standard — gauges + annulus pressure monitoring + periodic CBL/caliper.\n'
            'Comprehensive — full DTS/DAS fibre + wireless B-annulus + corrosion monitoring.'
        ),
    )
    _MON_DESC = {
        'minimal':       'P/T gauges + periodic wireline — lower detection, fewer planned interventions',
        'standard':      'Gauges + annulus pressure + CBL surveys — baseline program',
        'comprehensive': 'DTS/DAS + wireless B-annulus + corrosion monitoring — maximum early detection',
    }
    st.caption(_MON_DESC[monitoring_program])

    if view_mode != 'Executive':
        st.markdown('<div class="sb-section">🎯 Field Calibration</div>', unsafe_allow_html=True)
        _obs_events_sidebar = load_observed_events()
        _available_fields   = list_fields(_obs_events_sidebar)
        _field_options      = ['None (global assumptions)'] + _available_fields
        _field_choice       = st.selectbox(
            'Reference Field',
            options=_field_options,
            help=(
                'Select a field with observed operational data to calibrate the MTTF '
                'assumptions before running the simulation. Calibration factors are '
                'confidence-weighted so sparse datasets have limited influence.'
            ),
        )
        field_id = _field_choice if _field_choice != 'None (global assumptions)' else None
        if field_id:
            _n_obs = len(_obs_events_sidebar[_obs_events_sidebar['field_id'] == field_id])
            st.caption(f'{_n_obs} observed events loaded for **{field_id}**.')
        else:
            st.caption('No field selected — using global literature assumptions.')
    else:
        field_id = None

    st.markdown('<div class="sb-section">📋 Campaign Rules</div>', unsafe_allow_html=True)
    campaign_threshold = st.slider(
        'Campaign Threshold (wells)', 2, 15, 5,
        help='Trigger a batch campaign when this many workovers queue up',
    )
    max_deferral_years = st.slider(
        'Max Deferral (years)', 1, 5, 3,
        help='Force a campaign if the oldest deferred item exceeds this age',
    )
    co_location_discount_pct = st.slider(
        'Co-location Discount (%)', 0, 80, 25, step=5,
        help=(
            'When multiple components fail on the same well in the same year, '
            'the most expensive intervention is charged in full; additional '
            'components are charged this percentage of their standalone cost. '
            '25% = a $2.5M tubing pull co-located with a $0.2M gauge swap '
            'costs $2.5M + $50k, not $2.7M.'
        ),
    )
    co_location_discount_factor = co_location_discount_pct / 100

    st.markdown('<div class="sb-section">🔧 Fleet Equipment Coverage</div>', unsafe_allow_html=True)
    with st.expander('Configure penetration rates', expanded=False):
        st.caption(
            'Set the fraction of wells that have each component installed. '
            '100% = every well is equipped. Adjust for mixed-vintage fleets '
            'or phased installation programmes.'
        )
        fiber_pct = st.slider(
            'Fiber Optics (%)', 0, 100, 100, step=5,
            help='Permanent DTS/DAS fiber. Set <100% for fleets where only some wells have continuous fiber monitoring.',
        )
        civ_pct = st.slider(
            'Casing Isolation Valve (%)', 0, 100, 100, step=5,
            help='CO₂-specific annular barrier valve. Set <100% if CIVs are fitted to new-build wells only.',
        )
        flowmeter_pct = st.slider(
            'Injection Flowmeter (%)', 0, 100, 100, step=5,
            help='Per-well CO₂ injection flow measurement. Set <100% for projects with shared / cluster metering.',
        )
        gauge_pct = st.slider(
            'P/T Gauge (%)', 0, 100, 100, step=5,
            help='Downhole pressure/temperature gauge. Most wells are equipped; set <100% for older legacy wells.',
        )
        n_fiber  = round(fiber_pct / 100 * n_injectors)
        n_civ    = round(civ_pct / 100 * n_wells)
        n_flow   = round(flowmeter_pct / 100 * n_injectors)
        n_gauge  = round(gauge_pct / 100 * n_wells)
        st.caption(
            f'Fiber: {n_fiber}/{n_injectors} injectors · '
            f'CIV: {n_civ}/{n_wells} wells · '
            f'Flowmeter: {n_flow}/{n_injectors} injectors · '
            f'Gauge: {n_gauge}/{n_wells} wells'
        )

    component_penetration_rates = {
        'fiber_optics':       fiber_pct / 100,
        'casing_valve':       civ_pct / 100,
        'injection_flowmeter': flowmeter_pct / 100,
        'gauge':              gauge_pct / 100,
    }

    st.divider()
    run_btn = st.button('▶  Run Simulation', type='primary', use_container_width=True)

# ── Session state ─────────────────────────────────────────────────────────────
if 'results' not in st.session_state:
    st.session_state.results = None
if 'scenario_results' not in st.session_state:
    st.session_state.scenario_results = {}

# ── Run simulation ────────────────────────────────────────────────────────────
if run_btn:
    with st.status(f'Running {n_simulations:,} simulations…', expanded=True) as _sim_status:
        _progress_bar = st.progress(0.0)
        _step_text    = st.empty()

        def _on_progress(message: str, fraction: float):
            _step_text.markdown(f'`{message}`')
            _progress_bar.progress(min(fraction, 1.0))

        failure_df, campaign_log, annual_costs, lifecycle_summary, campaign_event_map = run_simulation(
            n_simulations=n_simulations,
            n_injectors=n_injectors,
            n_monitoring=n_monitoring,
            operating_years=operating_years,
            scenario_id=scenario_id,
            campaign_threshold=campaign_threshold,
            max_deferral_years=max_deferral_years,
            intervention_threshold=intervention_threshold,
            monitoring_program=monitoring_program,
            on_progress=_on_progress,
            component_penetration_rates=component_penetration_rates,
            co_location_discount_factor=co_location_discount_factor,
            field_id=field_id,
        )
        _sim_status.update(label='Simulation complete', state='complete', expanded=False)

    scenario_cfg = load_scenario_config()
    fpm = float(scenario_cfg.loc[scenario_id, 'failure_prob_multiplier']) \
          if scenario_id in scenario_cfg.index else 1.0

    annual_forecast      = build_annual_forecast(failure_df, operating_years)
    component_summary    = build_component_summary(failure_df)
    highest_risk         = get_highest_risk_component(failure_df)
    health_scores        = compute_asset_health_scores(
        failure_df, n_simulations, n_wells, operating_years)
    contributions        = compute_component_contributions(failure_df)

    component_assumptions_for_heatmap = load_component_assumptions()
    heatmap_df = compute_heatmap_data(
        component_assumptions_for_heatmap, operating_years, fpm
    )

    params = dict(
        n_injectors=n_injectors, n_monitoring=n_monitoring, n_wells=n_wells,
        operating_years=operating_years, n_simulations=n_simulations,
        scenario_id=scenario_id, failure_prob_multiplier=fpm,
        intervention_threshold=intervention_threshold,
        campaign_threshold=campaign_threshold, max_deferral_years=max_deferral_years,
        monitoring_program=monitoring_program,
        component_penetration_rates=component_penetration_rates,
        co_location_discount_factor=co_location_discount_factor,
        field_id=field_id,
        first_injection_year=first_injection_year,
    )
    narrative = generate_executive_narrative(
        failure_df, annual_forecast, campaign_log, lifecycle_summary, params)

    assumption_quality = load_assumption_quality()
    calibration_score  = compute_calibration_score(assumption_quality)
    qa_params = {**params, 'campaign_threshold': campaign_threshold,
                 'max_deferral_years': max_deferral_years}
    qa_metrics  = compute_qa_metrics(failure_df, campaign_log, lifecycle_summary, qa_params)
    qa_warnings = generate_qa_warnings(qa_metrics, qa_params)
    tornado_df  = compute_uncertainty_decomposition(contributions, component_assumptions_for_heatmap, n_simulations)

    # ── Field calibration results (for Calibration tab display) ──────────────
    _observed_events = load_observed_events()
    _cal_factors     = pd.DataFrame()
    _maturity_score  = {}
    _drift_alerts: list[dict] = []
    _cal_field_id    = field_id or (list_fields(_observed_events)[0] if not _observed_events.empty else None)
    if not _observed_events.empty:
        _comp_assum = load_component_assumptions()
        _cal_factors    = compute_calibration_factors(_observed_events, _comp_assum, _cal_field_id)
        _maturity_score = compute_maturity_score(_observed_events, _cal_factors, _cal_field_id)
        _drift_alerts   = detect_drift(_cal_factors)

    simulation_trace = build_simulation_trace(failure_df, campaign_event_map, params)
    worst_year_data  = compute_worst_year_breakdown(failure_df, campaign_log, annual_forecast, params)

    st.session_state.results = dict(
        failure_df=failure_df, campaign_log=campaign_log, annual_costs=annual_costs,
        lifecycle_summary=lifecycle_summary, annual_forecast=annual_forecast,
        component_summary=component_summary, highest_risk=highest_risk,
        health_scores=health_scores, contributions=contributions,
        narrative=narrative, params=params, heatmap_df=heatmap_df,
        assumption_quality=assumption_quality, calibration_score=calibration_score,
        qa_metrics=qa_metrics, qa_warnings=qa_warnings, tornado_df=tornado_df,
        observed_events=_observed_events, cal_factors=_cal_factors,
        maturity_score=_maturity_score, drift_alerts=_drift_alerts,
        cal_field_id=_cal_field_id,
        campaign_event_map=campaign_event_map,
        simulation_trace=simulation_trace,
        worst_year_data=worst_year_data,
    )

# ── Landing state ─────────────────────────────────────────────────────────────
if st.session_state.results is None:
    st.markdown("""
    <div style="text-align:center;padding:4rem 2rem;">
      <div style="font-size:2rem;font-weight:700;color:#e2e8f0;margin-bottom:.5rem;">
        CCS Workover Forecast
      </div>
      <div style="font-size:1rem;color:#64748b;margin-bottom:2rem;">
        Asset Integrity & Intervention Planning Platform
      </div>
      <div style="font-size:.85rem;color:#475569;max-width:520px;margin:0 auto;line-height:1.8;">
        Configure your asset in the sidebar, select a scenario, and run the Monte Carlo simulation
        to generate P10/P50/P90 workover demand, lifecycle cost, campaign plans, and risk analysis.
      </div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# ── Unpack results ────────────────────────────────────────────────────────────
r               = st.session_state.results
failure_df      = r['failure_df']
campaign_log    = r['campaign_log']
annual_costs    = r['annual_costs']
ls              = r['lifecycle_summary']
annual_forecast = r['annual_forecast']
component_summary = r['component_summary']
highest_risk    = r['highest_risk']
health_scores   = r['health_scores']
contributions   = r['contributions']
narrative       = r['narrative']
params          = r['params']
heatmap_df      = r.get('heatmap_df', pd.DataFrame())
assumption_quality = r.get('assumption_quality', pd.DataFrame())
calibration_score  = r.get('calibration_score', {})
qa_metrics         = r.get('qa_metrics', {})
qa_warnings        = r.get('qa_warnings', [])
tornado_df         = r.get('tornado_df', pd.DataFrame())
observed_events    = r.get('observed_events', pd.DataFrame())
cal_factors        = r.get('cal_factors', pd.DataFrame())
maturity_score     = r.get('maturity_score', {})
drift_alerts       = r.get('drift_alerts', [])
cal_field_id       = r.get('cal_field_id')
campaign_event_map = r.get('campaign_event_map', pd.DataFrame())
simulation_trace   = r.get('simulation_trace', pd.DataFrame())
worst_year_data    = r.get('worst_year_data', {})

scen_label = _SCENARIO_LABELS.get(params['scenario_id'], params['scenario_id'])
fpm        = params.get('failure_prob_multiplier', 1.0)

# ── Tab navigation ────────────────────────────────────────────────────────────
_ALL_TAB_DEFS = [
    ('overview',     '📊  Overview'),
    ('forecast',     '📈  Lifecycle Forecast'),
    ('risk',         '⚠️  Risk & Failure Modes'),
    ('campaigns',    '🏗  Campaign Planning'),
    ('economics',    '💰  Economics'),
    ('scenarios',    '🔀  Scenario Comparison'),
    ('calibration',  '🎯  Field Calibration'),
    ('qa',           '🔬  Model QA'),
    ('assumptions',  '⚙️  Assumptions'),
    ('trace',        '🔍  Simulation Trace'),
    ('journey',      '🛤  Well Journey'),
]
_MODE_TABS = {
    'Executive':   {'overview', 'scenarios'},
    'Engineering': {'overview', 'forecast', 'risk', 'campaigns', 'economics', 'scenarios',
                    'calibration', 'assumptions', 'trace', 'journey'},
    'Reviewer':    {'overview', 'assumptions', 'calibration', 'qa', 'trace', 'journey'},
    'Developer':   {t[0] for t in _ALL_TAB_DEFS},
}
_active_tabs  = [(k, lbl) for k, lbl in _ALL_TAB_DEFS if k in _MODE_TABS[view_mode]]
_tab_objects  = st.tabs([lbl for _, lbl in _active_tabs])
T = {k: obj for (k, _), obj in zip(_active_tabs, _tab_objects)}

# ═════════════════════════════════════════════════════════════════════════════
# TAB RENDER FUNCTIONS  (called inside  if 'key' in T: with T['key']:  below)
# ═════════════════════════════════════════════════════════════════════════════

def _render_overview():
    # ── Scenario header ───────────────────────────────────────────────────────
    scen_colors = {
        'base_case': '#3b82f6', 'conservative_design': '#10b981',
        'low_cost_design': '#f59e0b', 'high_corrosion': '#ef4444',
        'offshore_high_cost': '#8b5cf6',
    }
    sc = scen_colors.get(params['scenario_id'], '#3b82f6')
    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:1rem;margin-bottom:1.5rem;">
      <div style="background:{sc};border-radius:4px;padding:.25rem .75rem;
                  font-size:.7rem;font-weight:700;color:#fff;letter-spacing:.05em;">
        {scen_label.upper()}
      </div>
      <div style="color:#475569;font-size:.78rem;">
        {params['n_wells']} wells &nbsp;·&nbsp;
        {params['n_injectors']} injectors / {params['n_monitoring']} monitoring &nbsp;·&nbsp;
        {params['operating_years']}-year lifecycle &nbsp;·&nbsp;
        {params['n_simulations']:,} simulations
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Row 1 KPI cards — Workover Demand ────────────────────────────────────
    section('WORKOVER DEMAND')
    c1, c2, c3, c4 = st.columns(4)

    p50_wo        = ls.get('p50_workovers', 0)
    p90_wo        = ls.get('p90_workovers', 0)
    p50_peak_well = ls.get('p50_peak_annual_wells', 0)
    p90_peak_well = ls.get('p90_peak_annual_wells', 0)
    p50_peak_comp = ls.get('p50_peak_annual_demand', 0)
    p50_visits    = ls.get('p50_well_visits', 0)
    p50_camps     = ls.get('p50_campaigns', 0)

    wo_ratio   = p90_wo / max(p50_wo, 1)
    wo_risk    = 'red' if wo_ratio > 1.4 else 'amber' if wo_ratio > 1.2 else 'green'
    peak_risk  = 'red' if p50_peak_well > params['n_wells'] * 0.4 \
                 else 'amber' if p50_peak_well > params['n_wells'] * 0.2 else 'green'

    with c1:
        st.markdown(kpi_card(
            'P50 Rig Visits', f'{p50_visits:.0f}',
            'Full workover + light intervention well-year pairs over field life', 'blue'),
            unsafe_allow_html=True)
    with c2:
        st.markdown(kpi_card(
            'P90 Rig Visits', f'{ls.get("p90_well_visits", 0):.0f}',
            f'High-exposure scenario (+{(ls.get("p90_well_visits",0)/max(p50_visits,1)-1)*100:.0f}% vs P50)',
            wo_risk), unsafe_allow_html=True)
    with c3:
        st.markdown(kpi_card(
            'P50 Peak Wells / Year', f'{p50_peak_well:.0f} wells/yr',
            'Max distinct wells needing rig in any single year', peak_risk),
            unsafe_allow_html=True)
    with c4:
        st.markdown(kpi_card(
            'Expected Campaigns', f'{p50_camps:.0f}',
            'P50 batch mobilisations over lifecycle', 'purple'), unsafe_allow_html=True)

    if not failure_df.empty and 'intervention_type' in failure_df.columns:
        _rig_df  = failure_df[failure_df['intervention_type'].isin({'full_workover', 'light_intervention'})]
        _ann_w   = _rig_df.groupby(['simulation_id', 'year'])['well_id'].nunique().reset_index(name='_nw')
        _pk_rows = _ann_w.loc[_ann_w.groupby('simulation_id')['_nw'].idxmax()]
        _p50_pk_yr  = int(_pk_rows['year'].median())
        _wells_hit  = _pk_rows['_nw'].median()
        _avg_comp   = p50_peak_comp / max(_wells_hit, 1)
        st.caption(
            f'**{_wells_hit:.0f} wells** require rig mobilisation in Year {_p50_pk_yr} (worst year) — '
            f'avg {_avg_comp:.1f} component failures per well. '
            f'Multiple failures on the same well are addressed in a single rig visit. '
            f'Rigless interventions (wireline/CT) are tracked separately.'
        )

    st.markdown('<div style="height:.6rem"></div>', unsafe_allow_html=True)

    # ── Row 2 KPI cards — Economics ──────────────────────────────────────────
    section('LIFECYCLE ECONOMICS')
    c1, c2, c3, c4 = st.columns(4)

    p50_cost = ls.get('p50_lifecycle_cost', 0)
    p90_cost = ls.get('p90_lifecycle_cost', 0)
    cost_ratio = p90_cost / max(p50_cost, 1)
    cost_risk  = 'red' if cost_ratio > 1.4 else 'amber' if cost_ratio > 1.2 else 'green'

    with c1:
        st.markdown(kpi_card(
            'P50 Lifecycle Cost', format_cost(p50_cost),
            'Central cost estimate', 'blue'), unsafe_allow_html=True)
    with c2:
        st.markdown(kpi_card(
            'P90 Lifecycle Cost', format_cost(p90_cost),
            f'Contingency: {format_cost(p90_cost - p50_cost)}', cost_risk),
            unsafe_allow_html=True)
    with c3:
        st.markdown(kpi_card(
            'Primary Risk Driver', highest_risk.replace('_', ' ').title(),
            'Highest severity failure count', 'red'), unsafe_allow_html=True)
    with c4:
        thr = params.get('intervention_threshold', 0.90)
        if not failure_df.empty and 'trigger_type' in failure_df.columns:
            prev_count = (failure_df['trigger_type'] == 'preventive').sum()
            react_count = (failure_df['trigger_type'] == 'reactive').sum()
            prev_pct = prev_count / max(prev_count + react_count, 1) * 100
            thr_label = f'{thr*100:.0f}% — {prev_pct:.0f}% preventive'
        else:
            thr_label = f'{thr*100:.0f}% threshold'
        st.markdown(kpi_card(
            'Intervention Threshold', thr_label,
            'Preventive vs reactive split', 'purple'), unsafe_allow_html=True)

    st.markdown('<div style="height:.6rem"></div>', unsafe_allow_html=True)

    # ── Asset Health Overview ────────────────────────────────────────────────
    section('ASSET HEALTH OVERVIEW')
    left, right = st.columns([3, 2])

    with left:
        bars_html = '<div style="background:#111827;border:1px solid #1e293b;border-radius:8px;padding:1.2rem 1.4rem;">'
        for label, info in health_scores.items():
            bars_html += health_row(label, info['score'], info['status'], info['description'])
        bars_html += '</div>'
        st.markdown(bars_html, unsafe_allow_html=True)

    with right:
        section('EXECUTIVE FINDINGS')
        if narrative:
            for line in narrative:
                st.markdown(narrative_card(line), unsafe_allow_html=True)
        else:
            st.info('Run simulation to generate findings.')

    # ── Mode Comparison Panel ─────────────────────────────────────────────────
    if model_mode == 'Reliability Forecast':
        section('MODEL MODE — RELIABILITY FORECAST vs INTERVENTION PLANNING')
        m1, m2 = st.columns(2)
        with m1:
            st.markdown("""
            <div style="background:#0f172a;border:1px solid #1e293b;border-top:3px solid #3b82f6;
                        border-radius:0 0 8px 8px;padding:1rem 1.2rem;">
              <div style="font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.1em;
                          color:#3b82f6;margin-bottom:.75rem;">Reliability Forecast View</div>
              <p style="color:#94a3b8;font-size:.78rem;margin:0;line-height:1.65;">
                Pure component MTTF-based view. Shows <b style="color:#e2e8f0;">when</b> components
                are expected to fail based on the exponential reliability model.<br><br>
                Assumes all interventions occur at failure time — no batching,
                no deferred queue, no campaign optimisation.
              </p>
            </div>""", unsafe_allow_html=True)
        with m2:
            st.markdown("""
            <div style="background:#0f172a;border:1px solid #1e293b;border-top:3px solid #10b981;
                        border-radius:0 0 8px 8px;padding:1rem 1.2rem;">
              <div style="font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.1em;
                          color:#10b981;margin-bottom:.75rem;">Intervention Planning View (Active)</div>
              <p style="color:#94a3b8;font-size:.78rem;margin:0;line-height:1.65;">
                Adds campaign batching, deferred queue, and barrier-class prioritisation.
                Safety failures → emergency mobilisation. Production failures → deferred batch.
                Includes rig mob cost amortisation and CO₂ injection penalty.<br><br>
                Switch sidebar to <b style="color:#e2e8f0;">Intervention Planning</b> to simulate this mode.
              </p>
            </div>""", unsafe_allow_html=True)

    # ── KPI Traceability (Engineering / Developer only) ───────────────────────
    if view_mode != 'Executive':
        section('KPI TRACEABILITY — WHY ARE THESE NUMBERS WHAT THEY ARE?')
        component_assumptions_loaded = load_component_assumptions()

        with st.expander('What is driving the lifecycle cost?'):
            lines = explain_cost_driver(contributions, component_assumptions_loaded, params)
            for ln in lines:
                st.markdown(ln)

        with st.expander('Why is workover demand peaking when it does?'):
            lines = explain_peak_demand(annual_forecast, failure_df, params)
            for ln in lines:
                st.markdown(ln)

        with st.expander('Why does the model predict this many campaigns?'):
            lines = explain_campaign_count(campaign_log, ls, params)
            for ln in lines:
                st.markdown(ln)

        with st.expander('Why is this component the highest risk?'):
            lines = explain_highest_risk(highest_risk, contributions, component_assumptions_loaded, failure_df)
            for ln in lines:
                st.markdown(ln)


def _render_forecast():
    # ── Fan chart with toggle ─────────────────────────────────────────────────
    section('WORKOVER DEMAND FORECAST')
    fan_mode = st.radio('View', ['Annual', 'Cumulative'],
                        horizontal=True, label_visibility='collapsed')
    cumulative = fan_mode == 'Cumulative'
    st.plotly_chart(plot_workover_fan_chart(annual_forecast, cumulative=cumulative),
                    use_container_width=True, key='lf_fan')

    # ── Bathtub curve + cost fan ──────────────────────────────────────────────
    section('RELIABILITY LIFECYCLE & COST PROFILE')
    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(
            plot_bathtub_curve(failure_df, params['n_wells'],
                               params['n_simulations'], params['operating_years']),
            use_container_width=True, key='lf_bathtub')
    with col2:
        st.plotly_chart(plot_cost_fan_chart(annual_costs, params['operating_years']),
                        use_container_width=True, key='lf_cost_fan')

    # ── Secondary charts ──────────────────────────────────────────────────────
    section('CUMULATIVE PERFORMANCE & DISTRIBUTION')
    col3, col4 = st.columns(2)
    with col3:
        st.plotly_chart(plot_cumulative_workovers(failure_df), use_container_width=True, key='lf_cum_wo')
    with col4:
        st.plotly_chart(plot_lifecycle_cost_distribution(annual_costs), use_container_width=True, key='lf_cost_dist')

    with st.expander('Annual Forecast Data Table'):
        if not annual_forecast.empty:
            fmt = {c: '{:.1f}' for c in annual_forecast.columns if c != 'year'}
            st.dataframe(annual_forecast.style.format(fmt), use_container_width=True)


def _render_risk():
    # ── Risk matrix (flagship) ────────────────────────────────────────────────
    section('COMPONENT RISK MATRIX')
    col_rm, col_rs = st.columns([3, 2])
    with col_rm:
        st.plotly_chart(plot_risk_matrix(failure_prob_multiplier=fpm),
                        use_container_width=True, key='rm_matrix')
    with col_rs:
        section('TOP RISK CONTRIBUTORS')
        if not contributions.empty:
            for _, row in contributions.head(5).iterrows():
                comp_label = row['display_name']
                cost_pct   = row['cost_pct']
                event_pct  = row['event_pct']
                cost_m     = row['cost_m']
                color = '#ef4444' if cost_pct > 30 else '#f59e0b' if cost_pct > 15 else '#10b981'
                st.markdown(f"""
                <div style="background:#111827;border:1px solid #1e293b;border-left:3px solid {color};
                            border-radius:0 6px 6px 0;padding:.65rem .9rem;margin-bottom:.45rem;">
                  <div style="display:flex;justify-content:space-between;align-items:baseline;">
                    <span style="color:#e2e8f0;font-size:.8rem;font-weight:600;">{comp_label}</span>
                    <span style="color:{color};font-size:.75rem;font-weight:700;">{cost_pct:.0f}% of cost</span>
                  </div>
                  <div style="color:#64748b;font-size:.68rem;margin-top:.2rem;">
                    ${cost_m:.1f}M total &nbsp;·&nbsp; {event_pct:.0f}% of events
                  </div>
                </div>
                """, unsafe_allow_html=True)

    # ── Lifecycle heatmap (flagship) ──────────────────────────────────────────
    section('COMPONENT LIFECYCLE FAILURE PROBABILITY HEATMAP')
    st.plotly_chart(plot_lifecycle_heatmap(heatmap_df), use_container_width=True, key='rm_heatmap')

    # ── Failure charts ────────────────────────────────────────────────────────
    section('FAILURE MODE ANALYSIS')
    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(plot_component_treemap(failure_df), use_container_width=True, key='rm_treemap')
    with col2:
        st.plotly_chart(plot_severity_distribution(failure_df), use_container_width=True, key='rm_severity')

    col3, col4 = st.columns(2)
    with col3:
        st.plotly_chart(plot_failure_by_component(failure_df), use_container_width=True, key='rm_by_comp')
    with col4:
        st.plotly_chart(plot_intervention_type_split(failure_df), use_container_width=True, key='rm_int_split')

    with st.expander('Component Failure Detail Table'):
        if not component_summary.empty:
            st.dataframe(component_summary, use_container_width=True)

    with st.expander('Risk Matrix — Data Traceability'):
        st.markdown(
            '**Data source:** Component failure probabilities are derived from MTTF triangular '
            'distributions sampled across all Monte Carlo simulations. '
            'Consequence levels are defined in `data/assumptions/component_failure_assumptions.csv`. '
            'The failure probability multiplier for this scenario is **'
            f'{params.get("failure_prob_multiplier", 1.0):.2f}×** (applied to all P50 MTTF values).\n\n'
            '**Limitation:** The risk matrix uses scenario-adjusted P50 MTTF, not simulated failure '
            'counts per well, and should be interpreted as a relative ranking tool, not an absolute '
            'probability estimate.'
        )

    # ── Developer additions ───────────────────────────────────────────────────
    if view_mode == 'Developer':
        section('DEVELOPER — PEAK YEAR DEMAND DRILL-DOWN')
        st.caption(
            'Traces P50 Peak Annual Demand to its component sources. '
            'Shows which components drive the busiest year and why the headline number is what it is.'
        )

        # Find P50 peak year across all simulations
        _ann_demand = (
            failure_df.groupby(['simulation_id', 'year'])
            .size()
            .reset_index(name='n_events')
        )
        _peak_rows = _ann_demand.loc[
            _ann_demand.groupby('simulation_id')['n_events'].idxmax()
        ]
        _p50_peak_year  = int(_peak_rows['year'].median())
        _p50_peak_count = _peak_rows['n_events'].median()

        # Lifecycle multiplier active in that year (same for all components)
        _peak_df = failure_df[failure_df['year'] == _p50_peak_year]
        _peak_lc_mult = float(_peak_df['lifecycle_multiplier'].iloc[0]) if not _peak_df.empty else 1.0

        # KPI strip
        _n_sims = params['n_simulations']
        _first_inj_yr  = params.get('first_injection_year', 2030)
        _cal_peak_year = _first_inj_yr + _p50_peak_year - 1
        _n_comp_slots  = params['n_wells'] * failure_df['component'].nunique()
        _trigger_rate  = _p50_peak_count / _n_comp_slots * 100
        _k1, _k2, _k3, _k4 = st.columns(4)
        with _k1:
            st.metric('P50 Peak Year', f'Year {_p50_peak_year}',
                      delta=f'Cal. year {_cal_peak_year}', delta_color='off')
        with _k2:
            st.metric('Lifecycle Multiplier', f'{_peak_lc_mult:.2f}×')
        with _k3:
            st.metric('Avg Events in Peak Year', f'{_p50_peak_count:.0f}')
        with _k4:
            st.metric('Component Trigger Rate', f'{_trigger_rate:.1f}%',
                      help=f'{_p50_peak_count:.0f} events ÷ ({params["n_wells"]} wells × {failure_df["component"].nunique()} components)')

        # Component breakdown: avg events per simulation in the P50 peak year
        _bkd = (
            _peak_df
            .groupby(['display_name', 'intervention_type'])
            .agg(total_events=('simulation_id', 'count'))
            .reset_index()
        )
        _bkd['avg_per_sim']   = (_bkd['total_events'] / _n_sims).round(2)
        _bkd['pct_of_peak']   = (_bkd['total_events'] / max(_peak_df.shape[0], 1) * 100).round(1)
        _bkd = _bkd.sort_values('avg_per_sim', ascending=False).reset_index(drop=True)

        _bkd_fig = px.bar(
            _bkd, x='display_name', y='avg_per_sim', color='intervention_type',
            labels={
                'display_name': '',
                'avg_per_sim': 'Avg events in peak year (per simulation)',
                'intervention_type': 'Intervention type',
            },
            title=f'Year {_p50_peak_year} breakdown — avg component events per simulation (lifecycle mult: {_peak_lc_mult:.2f}×)',
            color_discrete_map={
                'full_workover':        '#ef4444',
                'light_intervention':   '#f59e0b',
                'rigless_intervention': '#3b82f6',
            },
        )
        _bkd_fig.update_layout(
            template='plotly_dark', height=380, xaxis_tickangle=-35,
            paper_bgcolor='#111827', plot_bgcolor='#0f172a',
        )
        st.plotly_chart(_bkd_fig, use_container_width=True, key='dev_peak_bkd_bar')

        _bkd_show = _bkd[['display_name', 'intervention_type', 'avg_per_sim', 'pct_of_peak']].copy()
        _bkd_show.columns = ['Component', 'Intervention Type', 'Avg events / sim', '% of peak demand']
        st.dataframe(_bkd_show, use_container_width=True, hide_index=True)

        st.caption(
            f'{_p50_peak_count:.0f} events across {params["n_wells"]} wells with '
            f'{failure_df["component"].nunique()} tracked components = '
            f'**{_trigger_rate:.1f}%** of component-well slots triggering in a single year.'
        )

        # ── Worst year narrative ─────────────────────────────────────────────
        _top_comps = _bkd.head(3)['display_name'].tolist()
        _top2_str  = ' and '.join(_top_comps[:2]) if len(_top_comps) >= 2 else _top_comps[0]
        _top2_pct  = float(_bkd.head(2)['pct_of_peak'].sum()) if len(_bkd) >= 2 else float(_bkd.head(1)['pct_of_peak'].sum())
        _prev_n  = (_peak_df['trigger_type'] == 'preventive').sum() / max(_n_sims, 1)
        _total_n = _peak_df.shape[0] / max(_n_sims, 1)
        _prev_pct = _prev_n / max(_total_n, 0.001) * 100
        _peak_wells = _peak_df.groupby('simulation_id')['well_id'].nunique().median()
        _rig_events = (_peak_df['intervention_type'] == 'full_workover').sum() / max(_n_sims, 1)
        _narrative_txt = (
            f"The peak intervention year is **{_cal_peak_year}** (Year **{_p50_peak_year}** of field "
            f"life), when the wear-out phase reaches **{_peak_lc_mult:.2f}×** baseline failure rates. "
            f"**{_top2_str}** are the primary drivers, together accounting for "
            f"**{_top2_pct:.0f}%** of peak-year events. "
            f"The simulated fleet requires **{int(_p50_peak_count)}** component interventions across "
            f"**{int(_peak_wells)}** wells, with **{_prev_pct:.0f}%** caught preventively before "
            f"failure and **{_rig_events:.1f}** requiring rig access (full workover)."
        )
        st.markdown(narrative_card(_narrative_txt), unsafe_allow_html=True)

        # Well-level drill-down: pick the representative simulation closest to P50
        section('DEVELOPER — PEAK YEAR WELL-LEVEL BREAKDOWN')
        st.caption(
            f'One representative simulation (closest to P50). '
            f'Shows which components failed on each well in Year {_p50_peak_year} '
            f'and whether a rig was required. '
            f'**Cost note:** each component is costed independently — '
            f'no bundling discount when multiple components are fixed in one well visit.'
        )

        _p50_sim_id = int(
            _peak_rows.loc[
                (_peak_rows['n_events'] - _p50_peak_count).abs().idxmin(),
                'simulation_id',
            ]
        )
        _well_peak_df = failure_df[
            (failure_df['simulation_id'] == _p50_sim_id) &
            (failure_df['year'] == _p50_peak_year)
        ]

        if not _well_peak_df.empty:
            _well_bkd = (
                _well_peak_df
                .groupby('well_id')
                .agg(
                    n_components   =('component',         'count'),
                    components     =('display_name',      lambda x: ' · '.join(sorted(x))),
                    rig_required   =('intervention_type', lambda x: 'full_workover' in x.values),
                    est_cost       =('estimated_cost',    'sum'),
                )
                .reset_index()
                .sort_values(['rig_required', 'n_components'], ascending=[False, False])
                .reset_index(drop=True)
            )
            _well_bkd['rig_required'] = _well_bkd['rig_required'].map({True: 'Yes', False: 'No'})
            _well_bkd['est_cost'] = (_well_bkd['est_cost'] / 1e6).round(2)
            _well_bkd.columns = ['Well', '# Components', 'Failed Components', 'Rig Required?', 'Est. Cost ($M)']

            _n_rig_wells = (_well_bkd['Rig Required?'] == 'Yes').sum()
            _n_rigless_wells = (_well_bkd['Rig Required?'] == 'No').sum()
            _k1, _k2, _k3 = st.columns(3)
            with _k1:
                st.metric('Wells Requiring Intervention', len(_well_bkd))
            with _k2:
                st.metric('Requiring Rig Workover', _n_rig_wells)
            with _k3:
                st.metric('Rigless / Light Only', _n_rigless_wells)

            st.dataframe(
                _well_bkd.style.apply(
                    lambda row: ['background-color:#1f0000;color:#fca5a5'
                                 if row['Rig Required?'] == 'Yes' else ''] * len(row),
                    axis=1,
                ),
                use_container_width=True,
                hide_index=True,
            )

        section('DEVELOPER — SAMPLED MTTF DISTRIBUTION')
        st.caption(
            'Distribution of MTTF values drawn for each component across all simulations and wells. '
            'Confirms the triangular P10/P90 distribution is being sampled correctly.'
        )
        _mttf_df = failure_df.drop_duplicates(['simulation_id', 'well_id', 'component'])[
            ['component', 'sampled_mttf']
        ]
        if not _mttf_df.empty:
            _mttf_fig = px.box(
                _mttf_df, x='component', y='sampled_mttf', color='component',
                labels={'sampled_mttf': 'Sampled MTTF (years)', 'component': ''},
                title='Sampled MTTF per component — triangular P10/P90 draws',
            )
            _mttf_fig.update_layout(
                template='plotly_dark', showlegend=False, height=400,
                paper_bgcolor='#111827', plot_bgcolor='#0f172a',
            )
            st.plotly_chart(_mttf_fig, use_container_width=True, key='dev_mttf_box')

        section('DEVELOPER — ADJUSTED FAILURE PROBABILITY vs OPERATING YEAR')
        st.caption(
            'Each point is one failure event. The upward trend in late years reflects the bathtub '
            'curve wear-out phase. Sampled from up to 3,000 events for readability.'
        )
        _prob_sample = failure_df.sample(min(3000, len(failure_df)), random_state=42)
        _prob_fig = px.scatter(
            _prob_sample, x='year', y='adjusted_probability',
            color='barrier_class', opacity=0.35,
            labels={
                'adjusted_probability': 'P(failure this year)',
                'year': 'Operating year',
                'barrier_class': 'Barrier class',
            },
            title='Adjusted failure probability vs operating year (3,000-event sample)',
        )
        _prob_fig.update_layout(
            template='plotly_dark', height=400,
            paper_bgcolor='#111827', plot_bgcolor='#0f172a',
        )
        st.plotly_chart(_prob_fig, use_container_width=True, key='dev_adj_prob')

        section('DEVELOPER — RAW FAILURE EVENT LOG (FIRST 500 ROWS)')
        st.caption('Download the complete log from the sidebar.')
        st.dataframe(failure_df.head(500), use_container_width=True)


def _render_campaigns():
    if campaign_log.empty:
        st.warning('No campaigns generated — try reducing the campaign threshold.')
    else:
        # ── Campaign schedule (main view) ─────────────────────────────────────
        section('CAMPAIGN SCHEDULE')
        cp_col1, cp_col2 = st.columns(2)
        with cp_col1:
            st.plotly_chart(plot_campaign_gantt(campaign_log, n_sample=12),
                            use_container_width=True, key='cp_gantt')
        with cp_col2:
            st.plotly_chart(plot_campaign_cost_by_year(campaign_log),
                            use_container_width=True, key='cp_cost_by_year')

        # ── Queue evolution ───────────────────────────────────────────────────
        section('DEFERRED WORKOVER QUEUE')
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(
                plot_deferred_queue_evolution(failure_df, campaign_log, params['operating_years']),
                use_container_width=True, key='cp_queue')
        with col2:
            st.plotly_chart(plot_immediate_vs_deferred(failure_df), use_container_width=True, key='cp_imm_vs_def')

        # ── Size & timeline ───────────────────────────────────────────────────
        section('CAMPAIGN CHARACTERISTICS')
        col3, col4 = st.columns(2)
        with col3:
            st.plotly_chart(plot_campaign_timeline(campaign_log), use_container_width=True, key='cp_timeline')
        with col4:
            st.plotly_chart(plot_campaign_size_distribution(campaign_log), use_container_width=True, key='cp_size_dist')

        # ── Stats table ───────────────────────────────────────────────────────
        with st.expander('Campaign Type Statistics'):
            stats = (
                campaign_log.groupby('campaign_type')
                .agg(
                    campaigns=('campaign_id', 'count'),
                    avg_wells=('n_wells', 'mean'),
                    avg_rig_workovers=('n_rig_workovers', 'mean'),
                    total_cost_m=('total_campaign_cost', lambda x: x.sum() / 1e6),
                    avg_mob_cost=('mobilisation_cost', 'mean'),
                )
                .round(1)
                .reset_index()
            )
            st.dataframe(stats, use_container_width=True)

        # ── Well-level demand & failure-mode grouping ─────────────────────────
        section('WELL-LEVEL DEMAND & FAILURE MODE GROUPING')
        if not failure_df.empty and 'intervention_type' in failure_df.columns:
            # Rig-requiring only: full workover + light intervention (excludes wireline/CT rigless)
            _int = failure_df[failure_df['intervention_type'].isin(
                {'full_workover', 'light_intervention'}
            )].copy()

            # P50 wells per year needing rig (for fan chart)
            _wpy = (
                _int.groupby(['simulation_id', 'year'])['well_id']
                .nunique()
                .reset_index(name='n_wells')
            )
            _wpy_q = (
                _wpy.groupby('year')['n_wells']
                .quantile([0.10, 0.50, 0.90])
                .unstack()
                .reset_index()
            )
            _wpy_q.columns = ['year', 'P10', 'P50', 'P90']

            # Failure-mode grouping: P50 wells per (year, component)
            _comp_wpy = (
                _int.groupby(['simulation_id', 'year', 'display_name'])['well_id']
                .nunique()
                .reset_index(name='n_wells')
                .groupby(['year', 'display_name'])['n_wells']
                .median()
                .reset_index()
            )
            # Keep only components that appear in at least one year
            _top_comps = (
                _comp_wpy.groupby('display_name')['n_wells'].sum()
                .nlargest(8).index.tolist()
            )
            _comp_wpy = _comp_wpy[_comp_wpy['display_name'].isin(_top_comps)]

            col_wl1, col_wl2 = st.columns(2)
            with col_wl1:
                import plotly.graph_objects as _go
                fig_wpy = _go.Figure()
                fig_wpy.add_trace(_go.Scatter(
                    x=list(_wpy_q['year']) + list(_wpy_q['year'][::-1]),
                    y=list(_wpy_q['P90']) + list(_wpy_q['P10'][::-1]),
                    fill='toself', fillcolor='rgba(239,68,68,0.15)',
                    line=dict(color='rgba(0,0,0,0)'), name='P10–P90', showlegend=True,
                ))
                fig_wpy.add_trace(_go.Scatter(
                    x=_wpy_q['year'], y=_wpy_q['P50'],
                    line=dict(color='#ef4444', width=2), name='P50 — Most Likely',
                ))
                fig_wpy.update_layout(
                    title='Wells Needing Rig per Year — P10/P50/P90',
                    xaxis_title='Year', yaxis_title='Distinct Wells',
                    template='plotly_dark', height=350, legend=dict(orientation='h'),
                )
                st.plotly_chart(fig_wpy, use_container_width=True, key='cp_wells_per_year')
                st.caption(
                    'Full workover + light intervention only. Each well counts once per year '
                    'regardless of how many components fail. '
                    'P50 peak = minimum rig capacity required in the worst year. '
                    'Rigless interventions (wireline, coiled tubing) are excluded.'
                )

            with col_wl2:
                fig_comp = px.bar(
                    _comp_wpy.sort_values(['year', 'n_wells'], ascending=[True, False]),
                    x='year', y='n_wells', color='display_name',
                    labels={'n_wells': 'Wells (P50)', 'year': 'Year',
                            'display_name': 'Failure Mode'},
                    title='P50 Wells by Failure Mode — Campaign Grouping Guide',
                    template='plotly_dark', height=350,
                    barmode='stack',
                )
                fig_comp.update_layout(legend=dict(orientation='h', y=-0.3))
                st.plotly_chart(fig_comp, use_container_width=True, key='cp_comp_grouping')
                st.caption(
                    'Rig-requiring interventions only. Wells with the same failure mode in the '
                    'same year are candidates for a shared campaign. A well with multiple '
                    'failure types appears in multiple stacks but requires only one rig visit.'
                )

        # ── Campaign Story ────────────────────────────────────────────────────
        section('CAMPAIGN STORY')
        st.caption('Select any campaign to understand why it existed, which wells participated, and what batching saved.')
        _all_camp_ids = sorted(campaign_log['campaign_id'].unique().tolist())
        _sel_camp = st.selectbox('Select campaign', _all_camp_ids,
                                  format_func=lambda c: c, key='camp_story_sel')
        if _sel_camp:
            _cs = build_campaign_story(_sel_camp, campaign_log, simulation_trace)
            if _cs:
                st.markdown(narrative_card(_cs['narrative']), unsafe_allow_html=True)
                _css_c1, _css_c2 = st.columns(2)
                with _css_c1:
                    st.markdown(f"""
                    <div style="background:#111827;border:1px solid #1e293b;border-radius:8px;padding:1rem;">
                      <div style="font-size:.6rem;font-weight:700;text-transform:uppercase;
                                  color:#64748b;letter-spacing:.1em;margin-bottom:.75rem;">CAMPAIGN DETAILS</div>
                      <table style="width:100%;border-collapse:collapse;font-size:.8rem;">
                        <tr><td style="color:#64748b;padding:.2rem 1rem .2rem 0;width:45%;">Type</td>
                            <td style="color:#e2e8f0;">{_cs['campaign_icon']} {_cs['campaign_type'].replace('_',' ').title()}</td></tr>
                        <tr><td style="color:#64748b;padding:.2rem 1rem .2rem 0;">Year</td>
                            <td style="color:#e2e8f0;">{_cs['year']}</td></tr>
                        <tr><td style="color:#64748b;padding:.2rem 1rem .2rem 0;">Wells</td>
                            <td style="color:#e2e8f0;">{_cs['n_wells']}</td></tr>
                        <tr><td style="color:#64748b;padding:.2rem 1rem .2rem 0;">Events</td>
                            <td style="color:#e2e8f0;">{_cs['n_events']}</td></tr>
                        <tr><td style="color:#64748b;padding:.2rem 1rem .2rem 0;">Rig workovers</td>
                            <td style="color:#e2e8f0;">{_cs['n_rig_workovers']}</td></tr>
                        <tr><td style="color:#64748b;padding:.2rem 1rem .2rem 0;">Total cost</td>
                            <td style="color:#10b981;font-weight:600;">{'${:,.0f}'.format(_cs['total_cost'])}</td></tr>
                        <tr><td style="color:#64748b;padding:.2rem 1rem .2rem 0;">Mob. savings</td>
                            <td style="color:#10b981;">{'${:,.0f}'.format(_cs['mob_savings']) if _cs['mob_savings'] > 0 else '—'}</td></tr>
                      </table>
                    </div>""", unsafe_allow_html=True)
                with _css_c2:
                    st.markdown(f"""
                    <div style="background:#111827;border:1px solid #1e293b;border-radius:8px;padding:1rem;height:100%;">
                      <div style="font-size:.6rem;font-weight:700;text-transform:uppercase;
                                  color:#64748b;letter-spacing:.1em;margin-bottom:.6rem;">WHY DID IT EXIST?</div>
                      <p style="font-size:.8rem;color:#94a3b8;line-height:1.65;margin-bottom:.75rem;">{_cs['why']}</p>
                      <div style="font-size:.6rem;font-weight:700;text-transform:uppercase;
                                  color:#64748b;letter-spacing:.1em;margin-bottom:.4rem;">COULD IT HAVE BEEN AVOIDED?</div>
                      <p style="font-size:.78rem;color:#94a3b8;line-height:1.65;margin:0;">{_cs['avoidable']}</p>
                    </div>""", unsafe_allow_html=True)
                if _cs['wells']:
                    st.caption(f"Wells in this campaign: {', '.join(_cs['wells'])}")
                if _cs['components']:
                    st.caption(f"Components addressed: {', '.join(_cs['components'])}")

        # ── Developer additions ───────────────────────────────────────────────
        if view_mode == 'Developer':
            section('DEVELOPER — IMMEDIATE vs DEFERRED BREAKDOWN BY COMPONENT')
            _imm_def = (
                failure_df
                .groupby(['component', 'immediate_or_deferred'])
                .size()
                .reset_index(name='count')
            )
            if not _imm_def.empty:
                _imm_fig = px.bar(
                    _imm_def, x='component', y='count', color='immediate_or_deferred',
                    barmode='stack',
                    labels={'count': 'Events', 'component': '', 'immediate_or_deferred': 'Response type'},
                    title='Immediate vs deferred events by component',
                    color_discrete_map={'immediate': '#ef4444', 'deferred': '#3b82f6'},
                )
                _imm_fig.update_layout(
                    template='plotly_dark', height=380,
                    paper_bgcolor='#111827', plot_bgcolor='#0f172a',
                )
                st.plotly_chart(_imm_fig, use_container_width=True, key='dev_imm_def')

            section('DEVELOPER — RAW CAMPAIGN LOG')
            st.caption('Complete campaign_log output including all scheduling metadata.')
            st.dataframe(campaign_log, use_container_width=True)


def _render_economics():
    # ── Waterfall + distribution ──────────────────────────────────────────────
    section('COST BREAKDOWN')
    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(
            plot_cost_waterfall(failure_df, annual_costs, n_simulations=params['n_simulations']),
            use_container_width=True, key='ec_waterfall')
    with col2:
        st.plotly_chart(plot_lifecycle_cost_distribution(annual_costs),
                        use_container_width=True, key='ec_cost_dist')

    # ── Component cost + annual trend ─────────────────────────────────────────
    section('COST DRIVERS & TRENDS')
    col3, col4 = st.columns(2)
    with col3:
        st.plotly_chart(plot_cost_by_component(failure_df), use_container_width=True, key='ec_by_comp')
    with col4:
        st.plotly_chart(plot_cost_fan_chart(annual_costs, params['operating_years']),
                        use_container_width=True, key='ec_cost_fan')

    # ── Economics summary cards ───────────────────────────────────────────────
    section('LIFECYCLE COST SUMMARY')
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(kpi_card('P10 Cost', format_cost(ls.get('p10_lifecycle_cost', 0)),
                             'Optimistic outcome', 'green'), unsafe_allow_html=True)
    with c2:
        st.markdown(kpi_card('P50 Cost', format_cost(ls.get('p50_lifecycle_cost', 0)),
                             'Central estimate', 'blue'), unsafe_allow_html=True)
    with c3:
        st.markdown(kpi_card('P90 Cost', format_cost(ls.get('p90_lifecycle_cost', 0)),
                             'High-cost scenario', 'red'), unsafe_allow_html=True)
    with c4:
        per_well = ls.get('p50_lifecycle_cost', 0) / max(params['n_wells'], 1)
        st.markdown(kpi_card('Cost per Well (P50)', format_cost(per_well),
                             'Average over lifecycle', 'amber'), unsafe_allow_html=True)

    with st.expander('Annual Economics Data Table'):
        if not annual_costs.empty:
            st.dataframe(annual_costs, use_container_width=True)

    with st.expander('Cost Breakdown — Data Traceability'):
        st.markdown(
            '**Mobilisation cost** = rig spread + logistics + permit fees. '
            'Loaded from `data/assumptions/cost_assumptions.csv` for the active scenario. '
            'Base case mob cost: **$2.0M/campaign**.\n\n'
            '**Intervention cost** = per-well equipment, fluids, and rig time. '
            'Full workover = **$2.5M**; rigless = **$0.25M** per event (base case).\n\n'
            '**Deferred injection penalty** = CO₂ storage revenue lost while a well awaits '
            'a deferred batch campaign. Rate: **$50k/day/well** (P50 carbon credit proxy — '
            'low confidence, expert judgement).\n\n'
            '**Uncertainty band (P10–P90):** driven primarily by MTTF spread on high-cost '
            'components (packer, tubing, cement barrier). See Model QA tab for full decomposition.'
        )


def _render_scenarios():
    # ── Capture / clear buttons ───────────────────────────────────────────────
    col_a, col_b, col_c = st.columns([2, 2, 8])
    with col_a:
        if st.button('Add current scenario', use_container_width=True):
            label = _SCENARIO_LABELS.get(params['scenario_id'], params['scenario_id'])
            mon = params.get('monitoring_program', 'standard')
            if mon != 'standard':
                label = f'{label} ({mon} monitoring)'
            st.session_state.scenario_results[label] = ls
            st.success(f'Added "{label}".')
    with col_b:
        if st.button('Clear all', use_container_width=True):
            st.session_state.scenario_results = {}
            st.rerun()

    if not st.session_state.scenario_results:
        st.markdown("""
        <div style="text-align:center;padding:3rem;color:#475569;font-size:.85rem;">
          Run multiple scenarios then click <b style="color:#94a3b8;">Add current scenario</b>
          to compare them side by side.
        </div>
        """, unsafe_allow_html=True)
    else:
        sr = st.session_state.scenario_results

        # Find best / worst by P50 lifecycle cost
        costs = {k: v.get('p50_lifecycle_cost', 0) for k, v in sr.items()}
        best_s  = min(costs, key=costs.get)
        worst_s = max(costs, key=costs.get)

        # ── Scenario cards ────────────────────────────────────────────────────
        section('SCENARIO COMPARISON CARDS')
        card_cols = st.columns(min(5, len(sr)))
        for i, (name, summary) in enumerate(sr.items()):
            highlight = 'best' if name == best_s else 'worst' if name == worst_s else ''
            with card_cols[i % min(5, len(sr))]:
                st.markdown(scenario_card(name, summary, highlight), unsafe_allow_html=True)
                st.markdown('<div style="height:.5rem"></div>', unsafe_allow_html=True)

        # ── Comparison charts ─────────────────────────────────────────────────
        section('COMPARATIVE ANALYSIS')
        comparison_df = build_scenario_comparison(sr)
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(plot_scenario_comparison(comparison_df), use_container_width=True, key='sc_cost_comp')
        with col2:
            st.plotly_chart(plot_scenario_workovers(comparison_df), use_container_width=True, key='sc_wo_comp')

        with st.expander('Scenario Comparison Table'):
            cols = ['scenario', 'p50_workovers', 'p90_workovers',
                    'p50_lifecycle_cost', 'p90_lifecycle_cost',
                    'p50_campaigns', 'p50_peak_annual_demand']
            show = [c for c in cols if c in comparison_df.columns]
            fmt  = {c: '${:,.0f}' for c in show if 'cost' in c}
            fmt.update({c: '{:.0f}' for c in show if 'cost' not in c and c != 'scenario'})
            st.dataframe(comparison_df[show].style.format(fmt), use_container_width=True)


def _render_calibration():
    _bc = _BORDER.get(maturity_score.get('color', 'red'), _BORDER['red'])
    _score = maturity_score.get('score', 0.0)
    _level = maturity_score.get('level', 'No data')
    _bkd   = maturity_score.get('breakdown', {})

    # ── Maturity score header ─────────────────────────────────────────────────
    section('RELIABILITY MATURITY SCORE')
    _m1, _m2, _m3, _m4 = st.columns(4)
    with _m1:
        st.markdown(kpi_card(
            'Maturity Score', f'{_score:.0f} / 100', _level,
            maturity_score.get('color', 'red')), unsafe_allow_html=True)
    with _m2:
        st.metric('Years of History', f'{_bkd.get("years_history", 0):.0f} yr')
    with _m3:
        st.metric('Observed Events', f'{_bkd.get("n_calibrable_events", 0)}')
    with _m4:
        st.metric('Components Covered',
                  f'{_bkd.get("n_components_covered", 0)} / 15')

    _maturity_ranges = [
        ('0–20',  'Concept study',    'No operational data — using literature assumptions only.'),
        ('20–40', 'Pre-FEED',         'Very early operations — calibration has minimal influence.'),
        ('40–60', 'FEED',             'Enough history to start adjusting conservative assumptions.'),
        ('60–80', 'Early operations', 'Meaningful calibration — model is becoming field-specific.'),
        ('80–100','Mature field',     'High confidence — model reflects this field\'s behaviour.'),
    ]
    with st.expander('Maturity scale reference', expanded=False):
        for rng, lbl, desc in _maturity_ranges:
            st.markdown(f'**{rng}** — **{lbl}**: {desc}')

    # ── Active field ──────────────────────────────────────────────────────────
    _active_field = params.get('field_id') or cal_field_id
    if _active_field:
        st.info(
            f'Calibration reference: **{_active_field}** · '
            f'{_bkd.get("n_calibrable_events", 0)} calibrable events · '
            f'{_bkd.get("years_history", 0):.0f} years of history',
            icon='🎯',
        )
        if params.get('field_id'):
            st.success(
                f'Field calibration **active** — MTTF assumptions were adjusted before '
                f'this simulation run using {_active_field} data.',
                icon='✅',
            )
        else:
            st.warning(
                f'Field data loaded for display only — run again with **{_active_field}** '
                f'selected in the sidebar to apply calibration to the simulation.',
                icon='⚠️',
            )
    else:
        st.info(
            'No field selected. Select a reference field in the sidebar to enable calibration.',
            icon='ℹ️',
        )

    # ── Drift alerts ─────────────────────────────────────────────────────────
    if drift_alerts:
        section('DRIFT DETECTION')
        for alert in drift_alerts:
            sev = alert['severity']
            icon = '🔴' if sev == 'critical' else '🟡' if sev == 'warning' else 'ℹ️'
            st.markdown(narrative_card(f'{icon}  {alert["message"]}'), unsafe_allow_html=True)
    else:
        section('DRIFT DETECTION')
        st.success('No significant model drift detected across calibrated components.', icon='✅')

    # ── Component calibration table ───────────────────────────────────────────
    section('CALIBRATION FACTORS BY COMPONENT')
    if cal_factors.empty:
        st.info('Load observed events and select a field to compute calibration factors.')
    else:
        _cf_display = cal_factors[[
            'display_name', 'mode_mttf', 'total_well_years', 'bathtub_exposure',
            'expected_failures', 'observed_failures', 'calibration_factor',
            'confidence', 'effective_factor', 'recommended_mttf',
        ]].copy()
        _cf_display.columns = [
            'Component', 'Mode MTTF (yr)', 'Raw Well-Years', 'Bathtub Exposure',
            'Expected Failures', 'Observed Failures', 'Calibration Factor',
            'Confidence', 'Effective Factor', 'Recommended MTTF (yr)',
        ]

        def _style_row(row):
            cf = row['Calibration Factor']
            if pd.isna(cf) or cf is None:
                return [''] * len(row)
            if cf > 1.5:
                return ['background-color:#1f0000;color:#fca5a5'] * len(row)
            if cf < 0.5:
                return ['background-color:#1f2a0a;color:#a3e635'] * len(row)
            return [''] * len(row)

        # Tooltip explaining the two exposure columns
        st.caption(
            '**Raw Well-Years**: simple sum of observation windows per well. '
            '**Bathtub Exposure**: well-years weighted by lifecycle phase multiplier '
            '(1.5× infant mortality yrs 1–2; 1.0× useful life; up to 1.8× wear-out). '
            'Expected Failures = base rate × Bathtub Exposure — so the calibration factor '
            'corrects only for MTTF error, not lifecycle phase effects.'
        )

        st.caption(
            'Red rows: observed failures significantly exceed model expectations (optimistic assumptions). '
            'Green rows: fewer failures than modelled (potentially conservative). '
            'Confidence weights the effective factor — low counts have limited influence.'
        )
        st.dataframe(
            _cf_display.style.apply(_style_row, axis=1).format({
                'Mode MTTF (yr)':        '{:.0f}',
                'Raw Well-Years':        '{:.0f}',
                'Bathtub Exposure':      '{:.0f}',
                'Expected Failures':     '{:.1f}',
                'Confidence':            '{:.0%}',
                'Effective Factor':      '{:.3f}',
                'Calibration Factor':    lambda x: f'{x:.3f}' if pd.notna(x) else '—',
                'Recommended MTTF (yr)': '{:.0f}',
            }),
            use_container_width=True,
            hide_index=True,
        )

    # ── Calibration factor chart ──────────────────────────────────────────────
    if not cal_factors.empty:
        _plot_df = cal_factors.dropna(subset=['calibration_factor']).copy()
        if not _plot_df.empty:
            _cf_fig = px.bar(
                _plot_df.sort_values('calibration_factor', ascending=True),
                x='calibration_factor',
                y='display_name',
                orientation='h',
                color='calibration_factor',
                color_continuous_scale=['#10b981', '#f59e0b', '#ef4444'],
                color_continuous_midpoint=1.0,
                labels={
                    'calibration_factor': 'Calibration Factor (observed / expected)',
                    'display_name': '',
                },
                title='Calibration factor by component — 1.0 = model matches observation',
                text='calibration_factor',
            )
            _cf_fig.update_traces(texttemplate='%{text:.2f}', textposition='outside')
            _cf_fig.add_vline(x=1.0, line_dash='dash', line_color='#94a3b8',
                              annotation_text='Model prediction', annotation_position='top right')
            _cf_fig.update_layout(
                template='plotly_dark', height=420, showlegend=False,
                paper_bgcolor='#111827', plot_bgcolor='#0f172a',
                coloraxis_showscale=False,
            )
            st.plotly_chart(_cf_fig, use_container_width=True, key='cal_factor_bar')

    # ── Recommended MTTF updates ──────────────────────────────────────────────
    if not cal_factors.empty:
        section('RECOMMENDED MTTF UPDATES')
        _updated = cal_factors[
            cal_factors['calibration_factor'].notna() &
            (abs(cal_factors['effective_factor'] - 1.0) > 0.02)
        ].copy()

        if _updated.empty:
            st.success('No MTTF updates recommended — calibration factors are within ±2% of 1.0.')
        else:
            st.caption(
                'Components where the effective calibration factor deviates more than 2% from 1.0. '
                'Select a field in the sidebar and rerun to apply these updates to the simulation.'
            )
            for _, row in _updated.sort_values('confidence', ascending=False).iterrows():
                eff    = row['effective_factor']
                delta  = (eff - 1.0) * 100
                arrow  = '↓' if eff > 1.0 else '↑'
                color  = 'red' if eff > 1.0 else 'green'
                change = f'{abs(delta):.0f}%'
                conf   = f'{row["confidence"]:.0%}'
                st.markdown(
                    f'**{row["display_name"]}**: P50 MTTF {row["mode_mttf"]:.0f} yr → '
                    f'**{row["recommended_mttf"]:.0f} yr** ({arrow} {change}, confidence {conf}) · '
                    f'Factor: {row["calibration_factor"]:.2f} effective: {eff:.3f}'
                )

    # ── Observed events log ───────────────────────────────────────────────────
    section('OBSERVED FIELD EVENTS')
    if observed_events.empty:
        st.info('No observed events found. Append rows to `data/observations/observed_events.csv`.')
    else:
        _obs_show = observed_events.copy()
        if _active_field:
            _obs_show = _obs_show[_obs_show['field_id'] == _active_field]
        st.caption(
            f'{len(_obs_show)} events for **{_active_field or "all fields"}**. '
            f'Append rows to `data/observations/observed_events.csv` to add new field history — '
            f'calibration updates automatically on next simulation run.'
        )
        st.dataframe(_obs_show, use_container_width=True, hide_index=True)

    # ── Calibration workflow ──────────────────────────────────────────────────
    with st.expander('How the calibration workflow works', expanded=False):
        st.markdown("""
**Operational workflow:**

1. A new intervention or inspection occurs in the field
2. An engineer appends a row to `data/observations/observed_events.csv` (append-only)
3. Select the field in the sidebar and re-run the simulation
4. The **Calibration** tab updates automatically with new factors and alerts
5. Calibration confidence increases as more events accumulate
6. When confidence is sufficient, apply the recommended MTTF updates

**Formula:**
- `expected_failures = Σ base_rate × bathtub_mult(t)` — summed over all observed well-years
- `calibration_factor = observed_failures / expected_failures`
- `confidence = min(observed_events / 20, 1.0)`
- `effective_factor = 1 + confidence × (calibration_factor − 1)`
- `calibrated_MTTF = base_MTTF / effective_factor`

`bathtub_mult(t)` is the lifecycle phase multiplier for year *t* of operation (1.5× infant
mortality years 1–2; 1.0× useful life; ramping to 1.8× wear-out). Weighting the expected
count by lifecycle phase ensures the calibration factor corrects only for genuine MTTF
underestimation — not for effects the simulation already applies via the bathtub curve.

The confidence weighting prevents a single event from rewriting the entire assumption set.
With 1 event, confidence = 5% — the calibrated MTTF shifts only 5% of the way toward the
observed rate. With 20+ events, the field evidence fully overrides the literature assumption.
        """)


def _render_qa():
    # ── Calibration Score ─────────────────────────────────────────────────────
    section('MODEL CALIBRATION SCORE')
    cs = calibration_score
    cal_score   = cs.get('score', 0)
    cal_level   = cs.get('level', 'Not computed')
    cal_color   = cs.get('color', 'red')
    cal_gaps    = cs.get('critical_gaps', [])
    cal_break   = cs.get('breakdown', {})
    n_assum     = cs.get('n_assumptions', 0)

    color_hex = {'green': '#10b981', 'amber': '#f59e0b', 'red': '#ef4444'}.get(cal_color, '#64748b')
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(kpi_card('Calibration Score', f'{cal_score:.0f}/100', cal_level, cal_color),
                    unsafe_allow_html=True)
    with c2:
        st.markdown(kpi_card('Assumptions Reviewed', str(n_assum), 'In quality register', 'blue'),
                    unsafe_allow_html=True)
    with c3:
        st.markdown(kpi_card('Critical Gaps', str(len(cal_gaps)),
                             'High-sensitivity / low-confidence parameters', 'red'),
                    unsafe_allow_html=True)
    with c4:
        lit_n = cal_break.get('literature', 0) + cal_break.get('oreda', 0)
        exp_n = cal_break.get('expert_judgement', 0) + cal_break.get('synthetic_assumption', 0)
        st.markdown(kpi_card('Literature-backed', f'{lit_n}/{n_assum}',
                             f'{exp_n} expert/synthetic assumptions', 'amber'),
                    unsafe_allow_html=True)

    st.markdown('<div style="height:.5rem"></div>', unsafe_allow_html=True)
    st.markdown(
        f'<div style="background:#0f172a;border-left:3px solid {color_hex};border-radius:0 6px 6px 0;'
        f'padding:.7rem 1rem;font-size:.8rem;color:#94a3b8;">'
        f'<b style="color:#e2e8f0;">Score interpretation:</b> The calibration score weights each '
        f'assumption by (source quality × confidence × sensitivity to output). '
        f'High-sensitivity assumptions with expert-judgement or synthetic sources reduce the score. '
        f'A score &lt;50 means at least one high-sensitivity parameter lacks literature backing — '
        f'outputs should be treated as order-of-magnitude estimates, not engineering commitments.'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Critical Gaps table ───────────────────────────────────────────────────
    if cal_gaps:
        section('CRITICAL CALIBRATION GAPS')
        st.caption(
            'These parameters have high output sensitivity but low source quality. '
            'They are the top priority for field calibration or literature review.'
        )
        gaps_df = pd.DataFrame(cal_gaps)[['parameter', 'component', 'source', 'confidence', 'sensitivity', 'notes']]
        def _highlight_gaps(row):
            return ['background-color:#1f0000;color:#fca5a5' if row['confidence'] == 'low' else ''] * len(row)
        st.dataframe(gaps_df.style.apply(_highlight_gaps, axis=1), use_container_width=True)

    # ── Sensitivity tornado ───────────────────────────────────────────────────
    section('SENSITIVITY TORNADO — MTTF ASSUMPTION IMPACT ON LIFECYCLE COST')
    if not tornado_df.empty:
        st.plotly_chart(plot_tornado_chart(tornado_df), use_container_width=True, key='qa_tornado')
        st.caption(
            'Analytical OAT (one-at-a-time) sensitivity. For each component, MTTF is varied from its '
            'P10 (pessimistic) to P90 (optimistic) value while all others stay at mode = (P10+P90)/2. '
            'ΔCost is estimated analytically via the ratio of annual failure probabilities — '
            'no re-simulation required. Components with the widest swing are the top priorities '
            'for field calibration.'
        )
    else:
        st.info('No sensitivity data — run simulation first.')

    # ── Validation Metrics grid ───────────────────────────────────────────────
    section('VALIDATION METRICS — MODEL SANITY CHECKS')
    if qa_metrics:
        cols_vm = st.columns(3)
        for i, (key, m) in enumerate(qa_metrics.items()):
            val  = m.get('value', 0)
            lo, hi = m.get('norm', (0, 1))
            in_range = lo <= val <= hi
            chip_color = '#10b981' if in_range else '#ef4444'
            chip_label = 'PASS' if in_range else 'OUT OF RANGE'
            with cols_vm[i % 3]:
                st.markdown(f"""
                <div style="background:#111827;border:1px solid #1e293b;border-radius:6px;
                            padding:.8rem 1rem;margin-bottom:.5rem;">
                  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.4rem;">
                    <span style="color:#94a3b8;font-size:.7rem;font-weight:600;">{m.get('label','')}</span>
                    <span style="background:{chip_color}22;color:{chip_color};font-size:.58rem;
                                 font-weight:700;padding:.1rem .4rem;border-radius:3px;">{chip_label}</span>
                  </div>
                  <div style="font-size:1.4rem;font-weight:700;color:#f1f5f9;">{val}</div>
                  <div style="color:#475569;font-size:.65rem;margin-top:.25rem;">{m.get('unit','')} &nbsp;|&nbsp; expected {lo}–{hi}</div>
                  <div style="color:#475569;font-size:.6rem;margin-top:.3rem;line-height:1.5;">{m.get('description','')}</div>
                </div>""", unsafe_allow_html=True)
    else:
        st.info('No validation metrics computed. Run the simulation first.')

    # ── Sanity Warnings ───────────────────────────────────────────────────────
    section('SANITY CHECKS & WARNINGS')
    sev_colors = {'critical': '#ef4444', 'warning': '#f59e0b', 'pass': '#10b981'}
    sev_icons  = {'critical': '🔴', 'warning': '🟡', 'pass': '🟢'}
    for w in qa_warnings:
        sev  = w.get('severity', 'warning')
        col  = sev_colors.get(sev, '#64748b')
        icon = sev_icons.get(sev, '⚪')
        st.markdown(f"""
        <div style="background:#0f172a;border:1px solid {col}40;border-left:3px solid {col};
                    border-radius:0 6px 6px 0;padding:.75rem 1rem;margin-bottom:.5rem;">
          <div style="font-size:.7rem;font-weight:700;color:{col};margin-bottom:.3rem;">
            {icon} {sev.upper()} — {w.get('metric','').replace('_',' ')}
          </div>
          <div style="color:#94a3b8;font-size:.78rem;line-height:1.6;">{w.get('message','')}</div>
          <div style="color:#475569;font-size:.65rem;margin-top:.35rem;font-style:italic;">
            Reference: {w.get('reference','')}
          </div>
        </div>""", unsafe_allow_html=True)

    # ── Campaign Type Breakdown ───────────────────────────────────────────────
    if not campaign_log.empty:
        section('CAMPAIGN TYPE BREAKDOWN')
        ct_stats = (
            campaign_log.groupby('campaign_type')
            .agg(
                count=('campaign_id', 'count'),
                avg_wells=('n_wells', 'mean'),
                total_cost_m=('total_campaign_cost', lambda x: x.sum() / 1e6),
            )
            .round(2).reset_index()
        )
        ct_stats['% of campaigns'] = (ct_stats['count'] / ct_stats['count'].sum() * 100).round(1)
        st.dataframe(ct_stats, use_container_width=True)


def _render_assumptions():
    # ── Assumption Quality Register ───────────────────────────────────────────
    section('ASSUMPTION QUALITY REGISTER')
    st.caption(
        'Each assumption is tagged with its source type, confidence level, and output sensitivity. '
        'This register supports peer review, regulatory audit, and targeted data acquisition.'
    )
    if not assumption_quality.empty:
        def _style_quality_row(row):
            styles = [''] * len(row)
            col_names = list(row.index)
            if 'source_type' in col_names:
                si = col_names.index('source_type')
                src = str(row.iloc[si]).lower()
                if src in ('synthetic_assumption', 'expert_judgement'):
                    styles[si] = 'color:#f59e0b;font-weight:600'
            if 'sensitivity_level' in col_names:
                hi = col_names.index('sensitivity_level')
                if 'high' in str(row.iloc[hi]).lower():
                    styles[hi] = 'color:#ef4444;font-weight:600'
            if 'confidence_level' in col_names:
                ci = col_names.index('confidence_level')
                if str(row.iloc[ci]).lower() == 'low':
                    styles[ci] = 'color:#ef4444'
            return styles

        st.dataframe(
            assumption_quality.style.apply(_style_quality_row, axis=1),
            use_container_width=True,
        )
        col_leg1, col_leg2 = st.columns(2)
        with col_leg1:
            st.markdown("""
            <div style="font-size:.68rem;color:#475569;line-height:1.9;">
            <b style="color:#94a3b8;">Source types (quality ranking):</b><br>
            🟢 <b>OREDA</b> (1.00) → <b>literature</b> (0.80) → <b>operator_analogue</b> (0.65)
            → 🟡 <b>expert_judgement</b> (0.40) → 🔴 <b>synthetic_assumption</b> (0.10)
            </div>""", unsafe_allow_html=True)
        with col_leg2:
            st.markdown("""
            <div style="font-size:.68rem;color:#475569;line-height:1.9;">
            <b style="color:#94a3b8;">Sensitivity weight:</b><br>
            🔴 <b>high impact</b> (1.0) — dominant in calibration score<br>
            🟡 <b>medium impact</b> (0.6) — moderate contribution<br>
            🟢 <b>low impact</b> (0.3) — minor influence on outputs
            </div>""", unsafe_allow_html=True)
    else:
        st.info('Assumption quality register not loaded — check data/assumptions/assumption_quality.csv')

    # ── Engineering Defensibility Panel ──────────────────────────────────────
    section('ENGINEERING DEFENSIBILITY')
    d_left, d_right = st.columns(2)
    with d_left:
        st.markdown("""
        <div style="background:#0f172a;border:1px solid #1e293b;border-top:3px solid #10b981;
                    border-radius:0 0 8px 8px;padding:1.1rem 1.2rem;">
          <div style="font-size:.65rem;font-weight:700;color:#10b981;text-transform:uppercase;
                      letter-spacing:.1em;margin-bottom:.75rem;">Model Strengths</div>
          <ul style="color:#94a3b8;font-size:.78rem;line-height:2.0;margin:0;padding-left:1.2rem;">
            <li>Vectorised Monte Carlo simulation — P10/P50/P90 output uncertainty quantified</li>
            <li>MTTF triangular distribution — captures epistemic uncertainty in component life</li>
            <li>Bathtub curve lifecycle phases — infant mortality, useful life, and wear-out modelled explicitly</li>
            <li>Barrier-class hierarchy — safety, production, monitoring, and flow assurance treated differently</li>
            <li>Emergency vs deferred campaign distinction — reflects real operational response logic</li>
            <li>Deferred injection penalty — captures CO₂ storage revenue at risk</li>
            <li>Assumption quality register — every parameter tagged with source type and confidence</li>
            <li>Scenario comparison — 5 scenarios covering corrosion, cost, and design variability</li>
          </ul>
        </div>""", unsafe_allow_html=True)
    with d_right:
        st.markdown("""
        <div style="background:#0f172a;border:1px solid #1e293b;border-top:3px solid #ef4444;
                    border-radius:0 0 8px 8px;padding:1.1rem 1.2rem;">
          <div style="font-size:.65rem;font-weight:700;color:#ef4444;text-transform:uppercase;
                      letter-spacing:.1em;margin-bottom:.75rem;">Model Limitations</div>
          <ul style="color:#94a3b8;font-size:.78rem;line-height:2.0;margin:0;padding-left:1.2rem;">
            <li>No CCS-specific field calibration data — all MTTF values from analogues or literature</li>
            <li>Component failures assumed independent — correlated degradation (e.g. tubing + packer) not modelled</li>
            <li>Cement barrier MTTF is synthetic — CO₂ carbonation data from pilots only</li>
            <li>Injectivity impairment: highly site-specific, depends on brine chemistry not captured</li>
            <li>Cost assumptions are North Sea analogues — may not apply to other geographies</li>
            <li>No reservoir geomechanics — pressure effects on wellbore integrity not included</li>
            <li>Carbon credit pricing ($50k/day) is highly uncertain — not used for decision-making</li>
            <li>Single-well barrier model — does not capture multi-well interference or shared infrastructure</li>
          </ul>
        </div>""", unsafe_allow_html=True)

    # ── How to Challenge ─────────────────────────────────────────────────────
    section('HOW TO CHALLENGE THIS MODEL')
    st.markdown("""
    <div style="background:#0f172a;border:1px solid #1e293b;border-radius:8px;padding:1.1rem 1.3rem;">
      <p style="color:#94a3b8;font-size:.78rem;line-height:1.9;margin:0;">
      <b style="color:#e2e8f0;">1. Replace synthetic assumptions:</b>
      Open <code>data/assumptions/assumption_quality.csv</code> and identify parameters flagged as
      <code>synthetic_assumption</code> or <code>expert_judgement</code> with high sensitivity.
      These should be the first targets for asset-specific data collection or literature review.<br><br>

      <b style="color:#e2e8f0;">2. Calibrate against field data:</b>
      If historical workover records exist, compare the simulated workover rate
      (<i>workovers_per_well</i> in Model QA) against the observed rate.
      Adjust P10/P90 MTTF values in <code>data/assumptions/component_failure_assumptions.csv</code>
      until the P50 simulated rate matches the historical mean.<br><br>

      <b style="color:#e2e8f0;">3. Stress-test critical gaps:</b>
      Manually vary the packer and cement MTTF P10 values by ±30% and observe the change in
      P50/P90 lifecycle cost. If the cost range exceeds 2×, the model is highly sensitive to
      these assumptions and calibration is essential before using outputs for CAPEX decisions.<br><br>

      <b style="color:#e2e8f0;">4. Validate campaign logic:</b>
      Compare Model QA → Campaign Frequency and Average Campaign Size against your operator's
      historical campaign records. If the simulated frequency is systematically higher or lower,
      adjust the campaign threshold slider accordingly.<br><br>

      <b style="color:#e2e8f0;">5. Apply to a specific asset:</b>
      Replace the scenario configuration in <code>data/assumptions/scenario_config.csv</code>
      with your asset's actual failure probability multiplier, offshore flag, and scssv configuration.
      </p>
    </div>
    """, unsafe_allow_html=True)

    # ── Raw assumption tables ─────────────────────────────────────────────────
    section('COMPONENT FAILURE ASSUMPTIONS')
    st.dataframe(load_component_assumptions(), use_container_width=True)

    section('INTERVENTION RULES')
    st.dataframe(load_intervention_rules(), use_container_width=True)

    section('COST ASSUMPTIONS — ACTIVE SCENARIO')
    st.warning(
        '**Illustrative values only.** The figures below are North Sea analogues used as starting '
        'points. Rig day-rates, workover costs, and deferred injection penalties vary significantly '
        'by geography, water depth, rig type, and operator contract. '
        'Edit `data/assumptions/cost_assumptions.csv` with your project-specific costs before '
        'using any outputs for commercial or investment decisions.',
        icon='⚠️',
    )
    cost_scen = 'offshore_high_cost' if params['scenario_id'] == 'offshore_high_cost' else 'base_case'
    costs_df  = pd.DataFrame(
        list(load_cost_assumptions(cost_scen).items()), columns=['Cost Item', 'Value (USD)']
    )
    st.dataframe(costs_df, use_container_width=True)

    section('SCENARIO CONFIGURATION')
    st.dataframe(load_scenario_config(), use_container_width=True)


def _render_trace():
    import numpy as np
    import plotly.graph_objects as go

    st.markdown("""
    <div style="margin-bottom:1.25rem;">
      <div style="font-size:1.05rem;font-weight:700;color:#e2e8f0;margin-bottom:.25rem;">
        Simulation Trace — Full Decision Audit
      </div>
      <div style="font-size:.78rem;color:#64748b;">
        Drill from portfolio peak year down to individual component decisions.
        Every Bernoulli draw, detection event, and campaign assignment is traceable.
      </div>
    </div>
    """, unsafe_allow_html=True)

    if simulation_trace.empty:
        st.info('Run the simulation to generate the trace.')
        return

    # ── Audit Mode toggle ─────────────────────────────────────────────────────
    audit_mode = st.toggle('Audit Mode — show all intermediate variables', value=False)

    # ── WORST YEAR EXPLAINABILITY ─────────────────────────────────────────────
    section('WORST YEAR EXPLAINABILITY')
    if worst_year_data:
        wd = worst_year_data
        _wc1, _wc2, _wc3, _wc4, _wc5 = st.columns(5)
        _wc1.metric('Peak Year (Field)', f"Year {wd['peak_year_field']}")
        _wc2.metric('Calendar Year', str(wd['peak_year_calendar']))
        _wc3.metric('Field Age', f"{wd['field_age']} yrs")
        _wc4.metric('P50 Interventions', f"{wd['p50_interventions']:.1f}")
        _wc5.metric('P50 Campaigns', f"{wd['n_campaigns_py']:.1f}")

        _wd_c1, _wd_c2 = st.columns(2)
        with _wd_c1:
            section('COMPONENT BREAKDOWN')
            if wd['comp_breakdown']:
                comp_df = pd.DataFrame(
                    list(wd['comp_breakdown'].items()),
                    columns=['Component', 'P50 Events/yr'],
                ).head(8)
                st.dataframe(comp_df, use_container_width=True, hide_index=True)
        with _wd_c2:
            section('CAMPAIGN BREAKDOWN')
            if wd['campaign_breakdown']:
                camp_df = pd.DataFrame(
                    list(wd['campaign_breakdown'].items()),
                    columns=['Campaign Type', 'P50 Campaigns/yr'],
                )
                st.dataframe(camp_df, use_container_width=True, hide_index=True)

        st.markdown(narrative_card(wd['narrative']), unsafe_allow_html=True)

    # ── PORTFOLIO FLOW (Sankey) ───────────────────────────────────────────────
    section('PORTFOLIO FLOW')
    st.caption(
        'Per-simulation average. Traces every failure from detection through barrier hierarchy '
        'to campaign type and intervention executed.'
    )
    _sk = build_sankey_data(simulation_trace, params.get('n_simulations', 1))
    if _sk and _sk.get('values'):
        import plotly.graph_objects as _go_sk
        _sk_fig = _go_sk.Figure(_go_sk.Sankey(
            arrangement='snap',
            node=dict(
                pad=18, thickness=20,
                line=dict(color='#0f172a', width=0.5),
                label=_sk['labels'],
                color=_sk['node_colors'],
                hovertemplate='%{label}: %{value:.1f} events/sim<extra></extra>',
            ),
            link=dict(
                source=_sk['sources'],
                target=_sk['targets'],
                value=_sk['values'],
                color=_sk['link_colors'],
                hovertemplate='%{source.label} → %{target.label}: %{value:.1f}/sim<extra></extra>',
            ),
        ))
        _sk_fig.update_layout(
            height=440,
            paper_bgcolor='#111827',
            font=dict(color='#94a3b8', size=11),
            margin=dict(l=20, r=20, t=10, b=10),
        )
        st.plotly_chart(_sk_fig, use_container_width=True)
    else:
        st.info('Sankey requires simulation results.')

    # ── CASCADING FILTERS ─────────────────────────────────────────────────────
    section('TRACE FILTERS')
    _all_sims = sorted(simulation_trace['simulation_id'].unique().tolist())
    _all_wells = sorted(simulation_trace['well_id'].unique().tolist())
    _all_comps = sorted(simulation_trace['component'].unique().tolist())
    _yr_min = int(simulation_trace['year_of_field_life'].min())
    _yr_max = int(simulation_trace['year_of_field_life'].max())

    _f1, _f2, _f3, _f4 = st.columns(4)
    with _f1:
        _sel_sims = st.multiselect(
            'Simulation ID(s)',
            options=_all_sims[:50],
            default=[_all_sims[0]] if _all_sims else [],
            help='Select one or more Monte Carlo simulation runs to inspect.',
        )
    with _f2:
        _sel_wells = st.multiselect(
            'Well(s)',
            options=_all_wells,
            default=[],
            placeholder='All wells',
        )
    with _f3:
        _yr_range = st.slider(
            'Year of Field Life',
            min_value=_yr_min, max_value=_yr_max,
            value=(_yr_min, _yr_max),
        )
    with _f4:
        _sel_comps = st.multiselect(
            'Component(s)',
            options=_all_comps,
            default=[],
            placeholder='All components',
        )

    # Build filtered trace
    _ft = simulation_trace.copy()
    if _sel_sims:
        _ft = _ft[_ft['simulation_id'].isin(_sel_sims)]
    if _sel_wells:
        _ft = _ft[_ft['well_id'].isin(_sel_wells)]
    if _sel_comps:
        _ft = _ft[_ft['component'].isin(_sel_comps)]
    _ft = _ft[
        (_ft['year_of_field_life'] >= _yr_range[0]) &
        (_ft['year_of_field_life'] <= _yr_range[1])
    ]

    st.caption(f'{len(_ft):,} events matching current filters')

    # ── INTERVENTION EXPLAINABILITY PANEL ─────────────────────────────────────
    if _sel_wells and len(_sel_wells) == 1 and _sel_sims and len(_sel_sims) == 1:
        section('INTERVENTION EXPLAINABILITY')
        _well_year_events = _ft.copy()
        if not _well_year_events.empty:
            _yr_options = sorted(_well_year_events['year_of_field_life'].unique().tolist())
            _exp_year = st.selectbox(
                'Inspect Year',
                options=_yr_options,
                index=len(_yr_options) - 1 if _yr_options else 0,
                format_func=lambda y: f"Year {y} (Cal. {params['first_injection_year'] + y - 1})",
            )
            _year_events = _well_year_events[_well_year_events['year_of_field_life'] == _exp_year]

            if not _year_events.empty:
                _ec1, _ec2 = st.columns([2, 1])
                with _ec1:
                    _drivers = _year_events.sort_values('annual_failure_probability', ascending=False)
                    _primary = _drivers.iloc[0]
                    _dn_col = 'display_name' if 'display_name' in _primary.index else 'component'

                    _det_text = 'Detected by monitoring.' if _primary.get('detected', False) else 'Undetected reactive failure.'
                    _defer_text = 'Yes' if _primary.get('can_defer', True) else 'No — immediate mobilisation required.'
                    _camp_id = _primary.get('campaign_id', None)
                    _camp_type = str(_primary.get('campaign_type', 'N/A'))
                    _camp_size = _primary.get('campaign_size', 'N/A')
                    _camp_str = f"{_camp_type.replace('_', ' ').title()} — Campaign {_camp_id}" if pd.notna(_camp_id) else 'Not yet assigned'
                    _cost_str = f"${float(_primary['intervention_cost']) / 1e6:.2f}M" if pd.notna(_primary.get('intervention_cost')) else 'N/A'
                    _days_str = f"{float(_primary['downtime_days']):.0f} days" if pd.notna(_primary.get('downtime_days')) else 'N/A'
                    _prob_str = f"{float(_primary['annual_failure_probability']) * 100:.1f}%" if pd.notna(_primary.get('annual_failure_probability')) else 'N/A'

                    st.markdown(f"""
                    <div style="background:#111827;border:1px solid #1e293b;border-left:4px solid #3b82f6;
                                border-radius:0 8px 8px 0;padding:1.1rem 1.3rem;margin-bottom:.75rem;">
                      <div style="font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.1em;
                                  color:#3b82f6;margin-bottom:.85rem;">WHY DID THIS INTERVENTION HAPPEN?</div>
                      <table style="width:100%;border-collapse:collapse;font-size:.8rem;">
                        <tr>
                          <td style="color:#64748b;padding:.2rem 1rem .2rem 0;width:40%;">Well</td>
                          <td style="color:#e2e8f0;font-weight:600;">{_sel_wells[0]}</td>
                        </tr>
                        <tr>
                          <td style="color:#64748b;padding:.2rem 1rem .2rem 0;">Year</td>
                          <td style="color:#e2e8f0;font-weight:600;">Year {_exp_year} (Cal. {params['first_injection_year'] + _exp_year - 1})</td>
                        </tr>
                        <tr>
                          <td style="color:#64748b;padding:.2rem 1rem .2rem 0;">Primary Driver</td>
                          <td style="color:#e2e8f0;font-weight:600;">{str(_primary[_dn_col]).replace('_',' ').title()} — {str(_primary.get('failure_mode','failure')).replace('_',' ')}</td>
                        </tr>
                        <tr>
                          <td style="color:#64748b;padding:.2rem 1rem .2rem 0;">Failure Probability</td>
                          <td style="color:#f59e0b;font-weight:600;">{_prob_str}</td>
                        </tr>
                        <tr>
                          <td style="color:#64748b;padding:.2rem 1rem .2rem 0;">Detection</td>
                          <td style="color:#e2e8f0;">{_det_text}</td>
                        </tr>
                        <tr>
                          <td style="color:#64748b;padding:.2rem 1rem .2rem 0;">Barrier Class</td>
                          <td style="color:#e2e8f0;">{str(_primary.get('barrier_class','N/A')).replace('_',' ').title()}</td>
                        </tr>
                        <tr>
                          <td style="color:#64748b;padding:.2rem 1rem .2rem 0;">Deferred</td>
                          <td style="color:#e2e8f0;">{_defer_text}</td>
                        </tr>
                        <tr>
                          <td style="color:#64748b;padding:.2rem 1rem .2rem 0;">Campaign Assignment</td>
                          <td style="color:#e2e8f0;">{_camp_str}</td>
                        </tr>
                        <tr>
                          <td style="color:#64748b;padding:.2rem 1rem .2rem 0;">Campaign Size</td>
                          <td style="color:#e2e8f0;">{_camp_size} wells</td>
                        </tr>
                        <tr>
                          <td style="color:#64748b;padding:.2rem 1rem .2rem 0;">Expected Downtime</td>
                          <td style="color:#e2e8f0;">{_days_str}</td>
                        </tr>
                        <tr>
                          <td style="color:#64748b;padding:.2rem 1rem .2rem 0;">Expected Cost</td>
                          <td style="color:#10b981;font-weight:600;">{_cost_str}</td>
                        </tr>
                      </table>
                    </div>
                    """, unsafe_allow_html=True)

                    if len(_drivers) > 1:
                        _supporting = _drivers.iloc[1:]
                        supp_names = ', '.join(
                            str(r[_dn_col]).replace('_', ' ').title()
                            for _, r in _supporting.iterrows()
                        )
                        st.caption(f'Supporting drivers in Year {_exp_year}: {supp_names}')

                with _ec2:
                    if audit_mode and not _year_events.empty:
                        st.markdown("""
                        <div style="background:#0f172a;border:1px solid #1e293b;border-radius:6px;
                                    padding:.9rem 1.1rem;font-size:.75rem;">
                          <div style="color:#3b82f6;font-weight:700;margin-bottom:.65rem;font-size:.65rem;
                                      text-transform:uppercase;letter-spacing:.1em;">AUDIT — INTERMEDIATE VARIABLES</div>
                        """, unsafe_allow_html=True)
                        for _, _ev in _year_events.iterrows():
                            _ev_name = str(_ev.get('display_name', _ev['component'])).replace('_', ' ').title()
                            _p10 = _ev.get('sampled_p10_mttf')
                            _p50 = _ev.get('sampled_p50_mttf')
                            _p90 = _ev.get('sampled_p90_mttf')
                            _eff = _ev.get('effective_mttf')
                            _bt  = _ev.get('bathtub_multiplier')
                            _ap  = _ev.get('annual_failure_probability')
                            _cf  = _ev.get('cumulative_failure_probability')
                            _bd  = _ev.get('bernoulli_draw')
                            _dp  = _ev.get('detection_probability')
                            _det = bool(_ev.get('detected', False))
                            _th  = bool(_ev.get('threshold_triggered', False))
                            _fo  = bool(_ev.get('failure_occurred', False))

                            def _fmt(v, pct=False, dec=2):
                                try:
                                    fv = float(v)
                                    if np.isnan(fv):
                                        return '—'
                                    return f'{fv*100:.1f}%' if pct else f'{fv:.{dec}f}'
                                except (TypeError, ValueError):
                                    return '—'

                            st.markdown(f"""
                            <div style="border-top:1px solid #1e293b;padding:.55rem 0 .35rem;margin-top:.4rem;">
                              <div style="color:#94a3b8;font-weight:600;margin-bottom:.4rem;">{_ev_name}</div>
                              <div style="color:#475569;line-height:2;font-size:.72rem;">
                                P10 MTTF: <span style="color:#e2e8f0;">{_fmt(_p10, dec=0)} yrs</span><br>
                                P50 MTTF: <span style="color:#e2e8f0;">{_fmt(_p50, dec=0)} yrs</span><br>
                                P90 MTTF: <span style="color:#e2e8f0;">{_fmt(_p90, dec=0)} yrs</span><br>
                                Effective (sampled): <span style="color:#f59e0b;">{_fmt(_eff, dec=1)} yrs</span><br>
                                Bathtub multiplier: <span style="color:#e2e8f0;">{_fmt(_bt, dec=2)}×</span><br>
                                Annual prob: <span style="color:#f59e0b;">{_fmt(_ap, pct=True)}</span><br>
                                Cumulative prob: <span style="color:#ef4444;">{_fmt(_cf, pct=True)}</span><br>
                                Bernoulli draw: <span style="color:#e2e8f0;">{_fmt(_bd, dec=4)}</span><br>
                                Failure: <span style="color:{'#ef4444' if _fo else '#10b981'};">{'TRUE' if _fo else 'FALSE'}</span><br>
                                Detection prob: <span style="color:#e2e8f0;">{_fmt(_dp, pct=True)}</span><br>
                                Detected: <span style="color:{'#10b981' if _det else '#64748b'};">{'TRUE' if _det else 'FALSE'}</span><br>
                                Threshold triggered: <span style="color:{'#8b5cf6' if _th else '#64748b'};">{'TRUE' if _th else 'FALSE'}</span>
                              </div>
                            </div>
                            """, unsafe_allow_html=True)
                        st.markdown('</div>', unsafe_allow_html=True)

    # ── TRACE TABLE ───────────────────────────────────────────────────────────
    section('TRACE TABLE')

    if not _ft.empty:
        _disp_cols_map = {
            'year_of_field_life':         'Year',
            'calendar_year':              'Cal. Year',
            'well_id':                    'Well',
            'component':                  'Component',
            'effective_mttf':             'Eff. MTTF (yrs)',
            'bathtub_multiplier':         'Bathtub ×',
            'annual_failure_probability': 'Fail Prob',
            'bernoulli_draw':             'Draw',
            'failure_occurred':           'Failure?',
            'detected':                   'Detected?',
            'barrier_class':              'Barrier',
            'can_defer':                  'Deferrable?',
            'threshold_triggered':        'Threshold?',
            'intervention_type':          'Intervention',
            'trigger_type':               'Trigger',
            'campaign_type':              'Campaign Type',
            'campaign_id':                'Campaign ID',
            'campaign_size':              'Camp. Wells',
            'intervention_cost':          'Cost (USD)',
            'downtime_days':              'Downtime (days)',
        }
        _disp_cols = [c for c in _disp_cols_map if c in _ft.columns]
        _disp = _ft[_disp_cols].rename(columns=_disp_cols_map).copy()

        if 'Fail Prob' in _disp.columns:
            _disp['Fail Prob'] = _disp['Fail Prob'].apply(
                lambda v: f'{float(v)*100:.1f}%' if pd.notna(v) else '—'
            )
        if 'Draw' in _disp.columns:
            _disp['Draw'] = _disp['Draw'].apply(
                lambda v: f'{float(v):.4f}' if pd.notna(v) and not (isinstance(v, float) and np.isnan(v)) else '—'
            )
        if 'Eff. MTTF (yrs)' in _disp.columns:
            _disp['Eff. MTTF (yrs)'] = _disp['Eff. MTTF (yrs)'].apply(
                lambda v: f'{float(v):.1f}' if pd.notna(v) else '—'
            )
        if 'Bathtub ×' in _disp.columns:
            _disp['Bathtub ×'] = _disp['Bathtub ×'].apply(
                lambda v: f'{float(v):.2f}' if pd.notna(v) else '—'
            )
        if 'Cost (USD)' in _disp.columns:
            _disp['Cost (USD)'] = _disp['Cost (USD)'].apply(
                lambda v: format_cost(float(v)) if pd.notna(v) else '—'
            )
        for _bcol in ['Failure?', 'Detected?', 'Deferrable?', 'Threshold?']:
            if _bcol in _disp.columns:
                _disp[_bcol] = _disp[_bcol].apply(
                    lambda v: 'TRUE' if v is True or v == True else 'FALSE'  # noqa: E712
                )
        for _scol in ['Intervention', 'Trigger', 'Campaign Type']:
            if _scol in _disp.columns:
                _disp[_scol] = _disp[_scol].apply(
                    lambda v: str(v).replace('_', ' ').title() if pd.notna(v) else '—'
                )

        # ── Icon columns ────────────────────────────────────────────────────
        if 'Barrier' in _disp.columns:
            _disp.insert(0, '🏷', _ft['barrier_class'].map(BARRIER_ICON).fillna('⚪'))
        if 'Trigger' in _disp.columns:
            _trig_map = {'reactive': '⚠️', 'preventive': '✅'}
            _disp.insert(1 if '🏷' in _disp.columns else 0, '▶', _ft['trigger_type'].map(_trig_map).fillna('❓'))
        if 'Campaign Type' in _disp.columns:
            _disp['Campaign Type'] = _ft['campaign_type'].map(
                lambda v: f"{CAMPAIGN_ICON.get(str(v), '📌')} {str(v).replace('_', ' ').title()}"
                if pd.notna(v) else '—'
            )

        MAX_ROWS = 2000
        if len(_disp) > MAX_ROWS:
            st.caption(f'Showing first {MAX_ROWS:,} of {len(_disp):,} rows — narrow your filters to see all.')
            _disp = _disp.head(MAX_ROWS)

        st.dataframe(_disp, use_container_width=True, hide_index=True)

        if audit_mode:
            with st.expander('Raw trace columns (audit mode)'):
                st.dataframe(_ft.head(500), use_container_width=True)
    else:
        st.info('No events match the current filters.')

    # ── SIMULATION TIMELINE ───────────────────────────────────────────────────
    if _sel_wells and len(_sel_wells) == 1 and _sel_sims and len(_sel_sims) == 1 and _sel_comps and len(_sel_comps) == 1:
        section('SIMULATION TIMELINE')
        _comp_trace = simulation_trace[
            (simulation_trace['simulation_id'] == _sel_sims[0]) &
            (simulation_trace['well_id'] == _sel_wells[0]) &
            (simulation_trace['component'] == _sel_comps[0])
        ].sort_values('year_of_field_life')

        if not _comp_trace.empty:
            _tl_fig = go.Figure()

            events_list = []
            for _, _ev in _comp_trace.iterrows():
                _yr = int(_ev['year_of_field_life'])
                _th = bool(_ev.get('threshold_triggered', False))
                _dt = bool(_ev.get('detected', False))
                _cy = _ev.get('campaign_year')

                if _th:
                    events_list.append((_yr, 'Threshold exceeded — preventive trigger', '#8b5cf6', 'diamond'))
                elif _dt:
                    events_list.append((_yr, 'Failure detected — planned intervention', '#f59e0b', 'star'))
                else:
                    events_list.append((_yr, 'Reactive failure', '#ef4444', 'circle'))

                if pd.notna(_cy) and int(float(_cy)) != _yr:
                    events_list.append((int(float(_cy)), 'Campaign execution', '#10b981', 'square'))

            _cum_vals = []
            for _, _ev in _comp_trace.iterrows():
                _yr = int(_ev['year_of_field_life'])
                _cv = _ev.get('cumulative_failure_probability')
                if pd.notna(_cv):
                    try:
                        _cum_vals.append((_yr, float(_cv) * 100))
                    except (TypeError, ValueError):
                        pass

            if _cum_vals:
                _cy_vals = [v[0] for v in _cum_vals]
                _cp_vals = [v[1] for v in _cum_vals]
                _tl_fig.add_trace(go.Scatter(
                    x=_cy_vals, y=_cp_vals,
                    mode='markers',
                    name='Cumulative Prob at Event',
                    marker=dict(color='#3b82f6', size=8),
                ))

            for _ey, _elabel, _ecol, _eshape in events_list:
                _tl_fig.add_trace(go.Scatter(
                    x=[_ey], y=[50],
                    mode='markers+text',
                    name=_elabel,
                    text=[_elabel],
                    textposition='top center',
                    marker=dict(color=_ecol, size=14, symbol=_eshape),
                    showlegend=True,
                ))

            _thr_pct = params.get('intervention_threshold', 0.90) * 100
            _tl_fig.add_hline(y=_thr_pct, line_dash='dot', line_color='#8b5cf6',
                               annotation_text=f'Threshold {_thr_pct:.0f}%')

            _tl_fig.update_layout(
                template='plotly_dark',
                paper_bgcolor='#111827',
                plot_bgcolor='#111827',
                height=320,
                margin=dict(l=40, r=20, t=20, b=40),
                yaxis_title='Cumulative Failure Prob (%)',
                xaxis_title='Year of Field Life',
                legend=dict(
                    orientation='h', yanchor='bottom', y=1.02,
                    xanchor='right', x=1, font=dict(size=10),
                ),
            )
            st.plotly_chart(_tl_fig, use_container_width=True)
            st.caption(
                'Select one simulation + one well + one component to view the timeline. '
                'Events shown are only those that resulted in interventions.'
            )

    # ── EXPORT ────────────────────────────────────────────────────────────────
    section('EXPORT TRACE')
    _exp_c1, _exp_c2, _exp_c3 = st.columns(3)
    with _exp_c1:
        _export_scope = st.radio(
            'Export scope',
            options=['Filtered view', 'Full trace'],
            horizontal=True,
            label_visibility='collapsed',
        )
    _export_df = _ft if _export_scope == 'Filtered view' else simulation_trace
    with _exp_c2:
        st.download_button(
            'Download CSV',
            data=_export_df.to_csv(index=False).encode('utf-8'),
            file_name='simulation_trace.csv',
            mime='text/csv',
            use_container_width=True,
        )
    with _exp_c3:
        import io
        _parquet_buf = io.BytesIO()
        _export_df.to_parquet(_parquet_buf, index=False)
        st.download_button(
            'Download Parquet',
            data=_parquet_buf.getvalue(),
            file_name='simulation_trace.parquet',
            mime='application/octet-stream',
            use_container_width=True,
        )


def _render_journey():
    import plotly.graph_objects as _go_j
    import plotly.express as _px_j

    st.markdown("""
    <div style="margin-bottom:1.25rem;">
      <div style="font-size:1.05rem;font-weight:700;color:#e2e8f0;margin-bottom:.25rem;">
        Well Journey — Single Well Operational History
      </div>
      <div style="font-size:.78rem;color:#64748b;">
        Follow a single well from commissioning to end of life.
        Every failure event, detection, campaign assignment, and cost is traceable.
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Engineering notes ─────────────────────────────────────────────────────
    with st.expander('Engineering Notes', expanded=False):
        st.markdown("""
**What this view shows**

A single Monte Carlo simulation run for one well. Results are stochastic — a different simulation run may produce a different event sequence. Use the portfolio-level tabs for statistically stable P10/P50/P90 estimates.

**Component health**

Health = (1 − cumulative failure probability) × 100. Post-intervention health reflects component-specific rejuvenation factors, not a blanket reset to 100%. Cement barriers and casing are capped below 100% because squeeze/patch repairs leave residual degradation. Rigless-intervention components (gauges, SSV, meters) are restored to near-100%.

**Remaining Useful Life (RUL)**

Estimated from the last observed annual failure probability on this simulation run. This is an indicative planning figure — not a re-simulation. Treat it as the approximate time window before the next intervention becomes likely at current degradation rates.

**Counterfactual view**

Shows the illustrative health trajectory if no interventions had ever been performed. Computed by propagating pre-intervention degradation forward without any health resets. This is **not** a re-simulation — it extrapolates existing reliability data for illustrative comparison only. Label: "Illustrative counterfactual — not a re-simulation."

**Calendar years**

Derived from the configured First Injection Year in the sidebar. Both field-life year (Yr N) and calendar year (CY YYYY) are shown throughout. If dates appear incorrect, verify the injection start year.
        """)

    if simulation_trace.empty:
        st.info('Run the simulation to explore well journeys.')
        return

    # ── Selectors ─────────────────────────────────────────────────────────────
    _jc1, _jc2 = st.columns(2)
    with _jc1:
        _j_wells = sorted(simulation_trace['well_id'].unique().tolist())
        _j_well  = st.selectbox('Select Well', _j_wells, key='journey_well')
    with _jc2:
        _j_sims = sorted(simulation_trace['simulation_id'].unique().tolist())[:50]
        _j_sim  = st.selectbox('Simulation Run', _j_sims, key='journey_sim')

    _first_yr = int(params['first_injection_year'])
    _op_yrs   = int(params['operating_years'])

    _jd = build_well_journey(
        simulation_trace, campaign_log,
        int(_j_sim), str(_j_well),
        _first_yr, _op_yrs,
    )

    if not _jd:
        st.warning(f'No events recorded for {_j_well} in simulation {_j_sim}.')
        return

    # ── Validation checks ─────────────────────────────────────────────────────
    _wt_v = _jd['wt']
    if 'calendar_year' in _wt_v.columns and 'year_of_field_life' in _wt_v.columns:
        _expected_cal = _wt_v['year_of_field_life'] + _first_yr - 1
        if not (_wt_v['calendar_year'] == _expected_cal).all():
            st.warning(
                'Calendar year formula inconsistency detected in trace data. '
                'Verify the First Injection Year in the sidebar.'
            )
    _inj_wo_mask = (
        (_wt_v['component'] == 'injectivity') & (_wt_v['intervention_type'] == 'full_workover')
        if not _wt_v.empty else pd.Series(dtype=bool)
    )
    if _inj_wo_mask.any():
        _n_inj_wo = int(_inj_wo_mask.sum())
        st.info(
            f'Note: Injectivity shows full workover for {_n_inj_wo} event(s) on this well — '
            'escalated from rigless due to repeat flow-assurance failures (by design).'
        )

    # ── Summary KPIs ──────────────────────────────────────────────────────────
    section('WELL SUMMARY')
    _jk1, _jk2, _jk3, _jk4, _jk5 = st.columns(5)
    _jk1.metric('Total Interventions', _jd['n_interventions'])
    _jk2.metric('Total Cost',          format_cost(_jd['total_cost']))
    _jk3.metric('Total Downtime',      f"{int(_jd['total_downtime'])} days")
    _jk4.metric('Reactive Events',     _jd['n_reactive'])
    _jk5.metric('Preventive Events',   _jd['n_preventive'])

    # ── Component health evolution ─────────────────────────────────────────────
    section('COMPONENT HEALTH EVOLUTION')
    st.caption(
        'Health = (1 − cumulative failure probability) × 100. '
        'Post-intervention health uses component-specific rejuvenation factors — not always 100%. '
        'Between events the curve is linearly interpolated — indicative only.'
    )
    _show_cfact = st.toggle(
        'Show counterfactual (what if no interventions?)', value=False, key='journey_cfact_toggle'
    )
    if _show_cfact:
        st.caption(
            ':orange[Illustrative counterfactual — not a re-simulation. '
            'Dashed lines show extrapolated degradation without any intervention resets.]'
        )
    _hdf = _jd['health_df']
    if not _hdf.empty:
        _hfig = _px_j.line(
            _hdf, x='year_of_field_life', y='health_pct', color='display_name',
            labels={'year_of_field_life': 'Field Life Year',
                    'health_pct': 'Component Health (%)', 'display_name': 'Component'},
            custom_data=['calendar_year'],
            template='plotly_dark',
        )
        _hfig.update_traces(
            hovertemplate='Yr %{x:.0f} (CY %{customdata[0]:.0f})<br>Health: %{y:.1f}%<extra></extra>'
        )
        if _show_cfact:
            _cfdf = _jd.get('counterfactual_health_df', pd.DataFrame())
            if not _cfdf.empty:
                for _cn in _cfdf['display_name'].unique():
                    _cf_c = _cfdf[_cfdf['display_name'] == _cn]
                    _hfig.add_trace(_go_j.Scatter(
                        x=_cf_c['year_of_field_life'], y=_cf_c['health_pct'],
                        mode='lines',
                        line=dict(dash='dot', width=2, color='#94a3b8'),
                        name=f'{_cn} (no interv.)',
                        opacity=0.75,
                        showlegend=False,
                        customdata=_cf_c[['calendar_year']].values,
                        hovertemplate=(
                            '<b>No-intervention counterfactual</b><br>'
                            f'{_cn}<br>'
                            'Yr %{x:.0f} (CY %{customdata[0]:.0f})<br>'
                            'Health: %{y:.1f}%<extra></extra>'
                        ),
                    ))
                # Single legend entry for all counterfactual traces
                _hfig.add_trace(_go_j.Scatter(
                    x=[None], y=[None], mode='lines',
                    line=dict(dash='dot', width=2, color='#94a3b8'),
                    name='No intervention (counterfactual)',
                    showlegend=True,
                ))
        _hfig.add_hline(y=80, line_dash='dot', line_color='#f59e0b',
                        annotation_text='Warning (80%)', annotation_font_size=10)
        _hfig.add_hline(y=60, line_dash='dot', line_color='#ef4444',
                        annotation_text='Critical (60%)', annotation_font_size=10)
        _tick_yrs = list(range(1, _op_yrs + 1, 5))
        if _op_yrs not in _tick_yrs:
            _tick_yrs.append(_op_yrs)
        _hfig.update_xaxes(
            tickmode='array',
            tickvals=_tick_yrs,
            ticktext=[f'Yr {y}<br>(CY {_first_yr + y - 1})' for y in _tick_yrs],
        )
        _hfig.update_layout(
            height=380, yaxis_range=[0, 108],
            paper_bgcolor='#111827', plot_bgcolor='#0f172a',
            legend=dict(orientation='h', y=-0.32),
            margin=dict(l=40, r=20, t=10, b=90),
        )
        st.plotly_chart(_hfig, use_container_width=True)

    # ── Operational timeline ───────────────────────────────────────────────────
    section('OPERATIONAL TIMELINE')
    for _card in _jd['story_cards']:
        _bc = _card['barrier_color']
        _ti = _card['trigger_icon']
        _bi = _card['barrier_icon']
        _inote = _card.get('intervention_note', '')
        _inote_html = (
            f'<div style="font-size:.69rem;color:#94a3b8;font-style:italic;margin-top:.25rem;">'
            f'&#9432; {_inote}</div>'
        ) if _inote else ''
        st.markdown(f"""
        <div style="border-left:3px solid {_bc};padding:.7rem 1rem;margin:.45rem 0;
                    background:#111827;border-radius:0 6px 6px 0;">
          <div style="font-size:.68rem;color:#64748b;text-transform:uppercase;
                      letter-spacing:.05em;margin-bottom:.2rem;">
            Yr {_card['year_field']} &nbsp;·&nbsp; CY {_card['cal_year']}
            &nbsp;·&nbsp; {_bi} {_card['barrier']} barrier
            &nbsp;·&nbsp; {_ti} {_card['trigger']}
          </div>
          <div style="font-size:.92rem;font-weight:700;color:{_bc};margin-bottom:.3rem;">
            {_card['component']}
          </div>
          <div style="font-size:.8rem;color:#e2e8f0;margin-bottom:.45rem;">{_card['what']}</div>
          <details>
            <summary style="font-size:.73rem;color:#475569;cursor:pointer;list-style:none;">
              ▸ Why did this happen?
            </summary>
            <div style="font-size:.76rem;color:#94a3b8;margin-top:.3rem;
                        padding:.4rem 0 0 .6rem;line-height:1.6;">{_card['why']}</div>
            <div style="font-size:.73rem;color:#64748b;margin-top:.3rem;padding-left:.6rem;">
              <em>Detection:</em> {_card['detection']}
            </div>
            <div style="font-size:.73rem;color:#64748b;margin-top:.2rem;padding-left:.6rem;">
              <em>Emergency?</em> {_card['emergency']}
            </div>
          </details>
          <div style="display:flex;gap:1.5rem;font-size:.71rem;color:#475569;margin-top:.45rem;
                      flex-wrap:wrap;">
            <span>🏗 {_card['campaign']}</span>
            <span>🔧 {_card['intervention']}</span>
            <span>💰 {_card['cost']}</span>
            <span>⏱ {_card['downtime']}</span>
          </div>
          {_inote_html}
        </div>
        """, unsafe_allow_html=True)

    # ── Remaining Useful Life ──────────────────────────────────────────────────
    section('REMAINING USEFUL LIFE (APPROXIMATE)')
    st.caption(
        'Estimated time to next intervention from the last observed event on this well. '
        'Based on last observed annual failure probability — indicative only, not a re-simulation. '
        'Next Risk Window = field-life year when health is projected to reach the critical threshold.'
    )
    _rul_df = _jd.get('rul_df', pd.DataFrame())
    if not _rul_df.empty:
        st.dataframe(_rul_df, use_container_width=True, hide_index=True)

    # ── Cost & downtime history ────────────────────────────────────────────────
    section('COST & DOWNTIME HISTORY')
    _cby = _jd['cost_by_year']
    if not _cby.empty:
        _jcol1, _jcol2 = st.columns(2)
        with _jcol1:
            _cfig = _px_j.bar(
                _cby, x='calendar_year', y='cost',
                labels={'calendar_year': 'Calendar Year', 'cost': 'Intervention Cost ($)'},
                template='plotly_dark', color_discrete_sequence=['#3b82f6'],
                custom_data=['year_of_field_life'],
            )
            _cfig.update_traces(
                hovertemplate='CY %{x} (Yr %{customdata[0]:.0f})<br>Cost: $%{y:,.0f}<extra></extra>'
            )
            _cfig.update_layout(height=280, paper_bgcolor='#111827', plot_bgcolor='#0f172a',
                                 margin=dict(l=40, r=10, t=20, b=40))
            st.plotly_chart(_cfig, use_container_width=True)
        with _jcol2:
            _dtfig = _px_j.bar(
                _cby, x='calendar_year', y='downtime',
                labels={'calendar_year': 'Calendar Year', 'downtime': 'Downtime (days)'},
                template='plotly_dark', color_discrete_sequence=['#f59e0b'],
                custom_data=['year_of_field_life'],
            )
            _dtfig.update_traces(
                hovertemplate='CY %{x} (Yr %{customdata[0]:.0f})<br>Downtime: %{y:.0f} days<extra></extra>'
            )
            _dtfig.update_layout(height=280, paper_bgcolor='#111827', plot_bgcolor='#0f172a',
                                  margin=dict(l=40, r=10, t=20, b=40))
            st.plotly_chart(_dtfig, use_container_width=True)

    # ── Decision path for one event ────────────────────────────────────────────
    section('DECISION PATH')
    st.caption('Select any event to see the exact chain of model decisions that produced it.')
    _wt = _jd['wt']
    _dp_options = [
        f"Yr {int(r['year_of_field_life'])} "
        f"(CY {int(r.get('calendar_year', _first_yr + int(r['year_of_field_life']) - 1))}) · "
        f"{r.get('display_name', r['component'])} · "
        f"{r.get('trigger_type', '?')}"
        for _, r in _wt.iterrows()
    ]
    if _dp_options:
        _dp_idx = st.selectbox(
            'Trace this event', range(len(_dp_options)),
            format_func=lambda i: _dp_options[i],
            key='journey_dp_sel',
        )
        _dp_row   = _wt.iloc[_dp_idx]
        _dp_nodes = build_decision_path(_dp_row)

        for _ni, _node in enumerate(_dp_nodes):
            _nc = _node['color']
            _detail_html  = (
                f'<div style="font-size:.7rem;color:#94a3b8;margin-top:.1rem;">'
                f'{_node["detail"]}</div>'
            ) if _node.get('detail') else ''
            _outcome_html = (
                f'<div style="font-size:.68rem;font-weight:700;color:{_nc};margin-top:.15rem;">'
                f'{_node["outcome"]}</div>'
            ) if _node.get('outcome') else ''
            _, _mid, _ = st.columns([1, 2, 1])
            with _mid:
                st.markdown(
                    f'<div style="border:2px solid {_nc};border-radius:8px;'
                    f'padding:.5rem 1.2rem;background:#111827;text-align:center;">'
                    f'<div style="font-size:.62rem;color:#64748b;text-transform:uppercase;'
                    f'letter-spacing:.08em;">{_node["label"]}</div>'
                    f'<div style="font-size:.95rem;font-weight:700;color:{_nc};'
                    f'margin:.15rem 0;">{_node["value"]}</div>'
                    f'{_detail_html}{_outcome_html}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                if _ni < len(_dp_nodes) - 1:
                    st.markdown(
                        '<div style="text-align:center;color:#475569;'
                        'font-size:1.1rem;line-height:1.8;">↓</div>',
                        unsafe_allow_html=True,
                    )


# ── Tab dispatch ──────────────────────────────────────────────────────────────
if 'overview' in T:
    with T['overview']:
        _render_overview()

if 'forecast' in T:
    with T['forecast']:
        _render_forecast()

if 'risk' in T:
    with T['risk']:
        _render_risk()

if 'campaigns' in T:
    with T['campaigns']:
        _render_campaigns()

if 'economics' in T:
    with T['economics']:
        _render_economics()

if 'scenarios' in T:
    with T['scenarios']:
        _render_scenarios()

if 'calibration' in T:
    with T['calibration']:
        _render_calibration()

if 'qa' in T:
    with T['qa']:
        _render_qa()

if 'assumptions' in T:
    with T['assumptions']:
        _render_assumptions()

if 'trace' in T:
    with T['trace']:
        _render_trace()

if 'journey' in T:
    with T['journey']:
        _render_journey()


# ── Sidebar downloads ─────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div class="sb-section">📥 Download Outputs</div>', unsafe_allow_html=True)

    def _csv(df):
        return df.to_csv(index=False).encode('utf-8')

    cols = st.columns(2)
    with cols[0]:
        if not failure_df.empty:
            st.download_button('Event Log', _csv(failure_df),
                               'failure_event_log.csv', 'text/csv', use_container_width=True)
        if not campaign_log.empty:
            st.download_button('Campaigns', _csv(campaign_log),
                               'campaign_log.csv', 'text/csv', use_container_width=True)
    with cols[1]:
        if not annual_forecast.empty:
            st.download_button('Forecast', _csv(annual_forecast),
                               'annual_forecast.csv', 'text/csv', use_container_width=True)
        if ls:
            st.download_button('Summary', _csv(pd.DataFrame([ls])),
                               'simulation_summary.csv', 'text/csv', use_container_width=True)
    if not annual_costs.empty:
        st.download_button('Economics', _csv(annual_costs),
                           'annual_economics.csv', 'text/csv', use_container_width=True)
