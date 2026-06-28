import streamlit as st
import pandas as pd

from src.simulation import run_simulation
from src.config_loader import (
    load_component_assumptions, load_intervention_rules,
    load_cost_assumptions, load_scenario_config,
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
    plot_campaign_gantt, plot_campaign_timeline, plot_campaign_size_distribution,
    plot_deferred_queue_evolution, plot_deferred_queue, plot_immediate_vs_deferred,
    plot_scenario_comparison, plot_scenario_workovers,
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
    'base_case':          'Base Case',
    'conservative_design': 'Conservative Design',
    'low_cost_design':    'Low-Cost Design',
    'high_corrosion':     'High Corrosion',
    'offshore_high_cost': 'Offshore High-Cost',
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

    st.markdown('<div class="sb-section">📋 Campaign Rules</div>', unsafe_allow_html=True)
    campaign_threshold = st.slider(
        'Campaign Threshold (wells)', 2, 15, 5,
        help='Trigger a batch campaign when this many workovers queue up',
    )
    max_deferral_years = st.slider(
        'Max Deferral (years)', 1, 5, 3,
        help='Force a campaign if the oldest deferred item exceeds this age',
    )

    st.divider()
    run_btn = st.button('▶  Run Simulation', type='primary', use_container_width=True)

# ── Session state ─────────────────────────────────────────────────────────────
if 'results' not in st.session_state:
    st.session_state.results = None
if 'scenario_results' not in st.session_state:
    st.session_state.scenario_results = {}

# ── Run simulation ────────────────────────────────────────────────────────────
if run_btn:
    with st.spinner(f'Running {n_simulations:,} simulations …'):
        failure_df, campaign_log, annual_costs, lifecycle_summary = run_simulation(
            n_simulations=n_simulations,
            n_injectors=n_injectors,
            n_monitoring=n_monitoring,
            operating_years=operating_years,
            scenario_id=scenario_id,
            campaign_threshold=campaign_threshold,
            max_deferral_years=max_deferral_years,
            intervention_threshold=intervention_threshold,
        )

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
    )
    narrative = generate_executive_narrative(
        failure_df, annual_forecast, campaign_log, lifecycle_summary, params)

    st.session_state.results = dict(
        failure_df=failure_df, campaign_log=campaign_log, annual_costs=annual_costs,
        lifecycle_summary=lifecycle_summary, annual_forecast=annual_forecast,
        component_summary=component_summary, highest_risk=highest_risk,
        health_scores=health_scores, contributions=contributions,
        narrative=narrative, params=params, heatmap_df=heatmap_df,
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

# ═════════════════════════════════════════════════════════════════════════════
# TAB 4 — CAMPAIGN PLANNING
# ═════════════════════════════════════════════════════════════════════════════
with tabs[3]:
    if campaign_log.empty:
        st.warning('No campaigns generated — try reducing the campaign threshold.')
    else:
        # ── Campaign schedule (main view) ─────────────────────────────────────
        section('CAMPAIGN SCHEDULE')
        st.plotly_chart(plot_campaign_gantt(campaign_log, n_sample=12),
                        use_container_width=True, key='cp_gantt')

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

# ═════════════════════════════════════════════════════════════════════════════
# TAB 6 — SCENARIO COMPARISON
# ═════════════════════════════════════════════════════════════════════════════
with tabs[5]:
    # ── Capture / clear buttons ───────────────────────────────────────────────
    col_a, col_b, col_c = st.columns([2, 2, 8])
    with col_a:
        if st.button('Add current scenario', use_container_width=True):
            label = _SCENARIO_LABELS.get(params['scenario_id'], params['scenario_id'])
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
# TAB 7 — ASSUMPTIONS
# ═════════════════════════════════════════════════════════════════════════════
with tabs[6]:
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
