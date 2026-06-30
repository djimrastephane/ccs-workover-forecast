import streamlit as st
import pandas as pd

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

    st.markdown('<div class="sb-section">🏗 Asset Configuration</div>', unsafe_allow_html=True)
    n_wells = st.slider('Total Wells', 10, 500, 100, step=10)
    injector_pct = st.slider('Injectors (%)', 50, 95, 80, step=5)
    n_injectors = int(n_wells * injector_pct / 100)
    n_monitoring = n_wells - n_injectors
    st.caption(f'{n_injectors} injectors · {n_monitoring} monitoring wells')
    operating_years = st.slider('Operating Life (years)', 10, 40, 30, step=5)

    st.markdown('<div class="sb-section">⚙️ Simulation</div>', unsafe_allow_html=True)
    scenario_id = st.selectbox(
        'Scenario',
        options=list(_SCENARIO_LABELS.keys()),
        format_func=lambda x: _SCENARIO_LABELS[x],
    )
    n_simulations = st.select_slider(
        'Monte Carlo Runs', options=[100, 250, 500, 1000, 2000], value=500,
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

    st.markdown('<div class="sb-section">📋 Campaign Rules</div>', unsafe_allow_html=True)
    campaign_threshold = st.slider(
        'Campaign Threshold (wells)', 2, 15, 5,
        help='Trigger a batch campaign when this many workovers queue up',
    )
    max_deferral_years = st.slider(
        'Max Deferral (years)', 1, 5, 3,
        help='Force a campaign if the oldest deferred item exceeds this age',
    )

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

        failure_df, campaign_log, annual_costs, lifecycle_summary = run_simulation(
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

    st.session_state.results = dict(
        failure_df=failure_df, campaign_log=campaign_log, annual_costs=annual_costs,
        lifecycle_summary=lifecycle_summary, annual_forecast=annual_forecast,
        component_summary=component_summary, highest_risk=highest_risk,
        health_scores=health_scores, contributions=contributions,
        narrative=narrative, params=params, heatmap_df=heatmap_df,
        assumption_quality=assumption_quality, calibration_score=calibration_score,
        qa_metrics=qa_metrics, qa_warnings=qa_warnings, tornado_df=tornado_df,
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

scen_label = _SCENARIO_LABELS.get(params['scenario_id'], params['scenario_id'])
fpm        = params.get('failure_prob_multiplier', 1.0)

# ── Tab navigation ────────────────────────────────────────────────────────────
tabs = st.tabs([
    '📊  Executive Summary',
    '📈  Lifecycle Forecast',
    '⚠️  Risk & Failure Modes',
    '🏗  Campaign Planning',
    '💰  Economics',
    '🔀  Scenario Comparison',
    '🔬  Model QA',
    '⚙️  Assumptions',
])

# ═════════════════════════════════════════════════════════════════════════════
# TAB 1 — EXECUTIVE SUMMARY
# ═════════════════════════════════════════════════════════════════════════════
with tabs[0]:
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

    p50_wo   = ls.get('p50_workovers', 0)
    p90_wo   = ls.get('p90_workovers', 0)
    p50_peak = ls.get('p50_peak_annual_demand', 0)
    p90_peak = ls.get('p90_peak_annual_demand', 0)
    p50_camps = ls.get('p50_campaigns', 0)

    # Determine risk context
    wo_ratio = p90_wo / max(p50_wo, 1)
    wo_risk  = 'red' if wo_ratio > 1.4 else 'amber' if wo_ratio > 1.2 else 'green'
    peak_risk = 'red' if p50_peak > 15 else 'amber' if p50_peak > 8 else 'green'

    with c1:
        st.markdown(kpi_card(
            'P50 Workovers', f'{p50_wo:.0f}',
            'Most likely total over field life', 'blue'), unsafe_allow_html=True)
    with c2:
        st.markdown(kpi_card(
            'P90 Workovers', f'{p90_wo:.0f}',
            f'High-exposure scenario (+{(wo_ratio-1)*100:.0f}% vs P50)', wo_risk),
            unsafe_allow_html=True)
    with c3:
        st.markdown(kpi_card(
            'P50 Peak Annual Demand', f'{p50_peak:.0f} /yr',
            'Maximum annual intervention rate', peak_risk), unsafe_allow_html=True)
    with c4:
        st.markdown(kpi_card(
            'Expected Campaigns', f'{p50_camps:.0f}',
            'P50 batch mobilisations over lifecycle', 'purple'), unsafe_allow_html=True)

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

    # ── KPI Traceability ──────────────────────────────────────────────────────
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

# ═════════════════════════════════════════════════════════════════════════════
# TAB 2 — LIFECYCLE FORECAST
# ═════════════════════════════════════════════════════════════════════════════
with tabs[1]:
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

# ═════════════════════════════════════════════════════════════════════════════
# TAB 3 — RISK & FAILURE MODES
# ═════════════════════════════════════════════════════════════════════════════
with tabs[2]:
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

# ═════════════════════════════════════════════════════════════════════════════
# TAB 4 — CAMPAIGN PLANNING
# ═════════════════════════════════════════════════════════════════════════════
with tabs[3]:
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

# ═════════════════════════════════════════════════════════════════════════════
# TAB 5 — ECONOMICS
# ═════════════════════════════════════════════════════════════════════════════
with tabs[4]:
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

# ═════════════════════════════════════════════════════════════════════════════
# TAB 6 — SCENARIO COMPARISON
# ═════════════════════════════════════════════════════════════════════════════
with tabs[5]:
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

# ═════════════════════════════════════════════════════════════════════════════
# TAB 7 — MODEL QA
# ═════════════════════════════════════════════════════════════════════════════
with tabs[6]:
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


# ═════════════════════════════════════════════════════════════════════════════
# TAB 8 — ASSUMPTIONS
# ═════════════════════════════════════════════════════════════════════════════
with tabs[7]:
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
    cost_scen = 'offshore_high_cost' if params['scenario_id'] == 'offshore_high_cost' else 'base_case'
    costs_df  = pd.DataFrame(
        list(load_cost_assumptions(cost_scen).items()), columns=['Cost Item', 'Value (USD)']
    )
    st.dataframe(costs_df, use_container_width=True)

    section('SCENARIO CONFIGURATION')
    st.dataframe(load_scenario_config(), use_container_width=True)

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
