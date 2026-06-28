"""
Plotting module — all charts use a consistent dark industrial theme.
"""
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np

# ── Colour palette ────────────────────────────────────────────────────────────
_RED     = '#ef4444'
_AMBER   = '#f59e0b'
_GREEN   = '#10b981'
_BLUE    = '#3b82f6'
_PURPLE  = '#8b5cf6'
_CYAN    = '#06b6d4'
_ORANGE  = '#f97316'
_SLATE   = '#64748b'

_RED_A    = 'rgba(239,68,68,0.15)'
_AMBER_A  = 'rgba(245,158,11,0.15)'
_GREEN_A  = 'rgba(16,185,129,0.15)'
_BLUE_A   = 'rgba(59,130,246,0.15)'
_PURPLE_A = 'rgba(139,92,246,0.15)'

_SEVERITY = {'low': _GREEN, 'medium': _AMBER, 'high': _RED}
_ITYPE    = {
    'full_workover':       _RED,
    'light_intervention':  _AMBER,
    'rigless_intervention': _BLUE,
    'monitor_only':        _SLATE,
}
_CTYPE    = {
    'immediate':       _RED,
    'deferred_batch':  _BLUE,
    'end_of_life':     _PURPLE,
    'end_of_life_cleanup': _PURPLE,
}


# ── Dark theme helper ─────────────────────────────────────────────────────────
def _dark(fig: go.Figure, height: int = 420) -> go.Figure:
    fig.update_layout(
        template='plotly_dark',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(255,255,255,0.02)',
        height=height,
        font=dict(family='Inter,-apple-system,sans-serif', color='#94a3b8', size=11),
        title_font=dict(color='#e2e8f0', size=13, family='Inter,-apple-system,sans-serif'),
        legend=dict(bgcolor='rgba(0,0,0,0)', bordercolor='rgba(0,0,0,0)',
                    font=dict(color='#94a3b8', size=10)),
        margin=dict(l=44, r=20, t=50, b=40),
    )
    fig.update_xaxes(gridcolor='#1e293b', linecolor='#334155',
                     tickfont=dict(color='#64748b', size=10))
    fig.update_yaxes(gridcolor='#1e293b', linecolor='#334155',
                     tickfont=dict(color='#64748b', size=10))
    return fig


def _ribbon(fig, x, lo, hi, band_color, name):
    """P10–P90 uncertainty ribbon."""
    fig.add_trace(go.Scatter(x=x, y=hi, mode='lines',
                             line=dict(width=0), showlegend=False, hoverinfo='skip'))
    fig.add_trace(go.Scatter(x=x, y=lo, mode='lines',
                             line=dict(width=0), fill='tonexty',
                             fillcolor=band_color, showlegend=True, name=name,
                             hoverinfo='skip'))


# ── Flagship: Workover Fan Chart ──────────────────────────────────────────────
def plot_workover_fan_chart(df: pd.DataFrame, cumulative: bool = False) -> go.Figure:
    """Main uncertainty fan chart for workover demand."""
    fig = go.Figure()
    if df.empty:
        return _dark(fig)

    yr = df['year']
    if cumulative:
        p10 = df['p10_workovers'].cumsum()
        p50 = df['p50_workovers'].cumsum()
        p90 = df['p90_workovers'].cumsum()
        title = 'Cumulative Workover Demand — P10 / P50 / P90'
        ylabel = 'Cumulative Workovers'
    else:
        p10, p50, p90 = df['p10_workovers'], df['p50_workovers'], df['p90_workovers']
        title = 'Annual Workover Demand — P10 / P50 / P90'
        ylabel = 'Workovers per Year'

    _ribbon(fig, yr, p10, p90, _RED_A, 'P10–P90 Uncertainty Band')
    fig.add_trace(go.Scatter(x=yr, y=p90, mode='lines', line=dict(color=_RED, width=1, dash='dot'),
                             name='P90', opacity=0.7))
    fig.add_trace(go.Scatter(x=yr, y=p50, mode='lines+markers',
                             line=dict(color=_RED, width=3),
                             marker=dict(size=4, color=_RED),
                             name='P50 — Most Likely'))
    fig.add_trace(go.Scatter(x=yr, y=p10, mode='lines', line=dict(color=_RED, width=1, dash='dot'),
                             name='P10', opacity=0.7))

    fig.update_layout(title=title, xaxis_title='Year', yaxis_title=ylabel,
                      legend=dict(orientation='h', x=0, y=1.08))
    return _dark(fig, 460)


def plot_cost_fan_chart(annual_costs: pd.DataFrame, operating_years: int) -> go.Figure:
    """Annual total cost P10/P50/P90 fan chart."""
    fig = go.Figure()
    if annual_costs.empty:
        return _dark(fig)

    all_sims = annual_costs['simulation_id'].unique()
    pivot = (
        annual_costs.pivot_table(index='simulation_id', columns='year',
                                  values='total_cost', aggfunc='sum')
        .reindex(index=all_sims, fill_value=0)
    )
    years = list(range(1, operating_years + 1))
    p10 = [pivot[yr].quantile(0.10) / 1e6 if yr in pivot.columns else 0 for yr in years]
    p50 = [pivot[yr].quantile(0.50) / 1e6 if yr in pivot.columns else 0 for yr in years]
    p90 = [pivot[yr].quantile(0.90) / 1e6 if yr in pivot.columns else 0 for yr in years]

    _ribbon(fig, years, p10, p90, _AMBER_A, 'P10–P90 Cost Range')
    fig.add_trace(go.Scatter(x=years, y=p90, mode='lines',
                             line=dict(color=_AMBER, width=1, dash='dot'), name='P90', opacity=0.7))
    fig.add_trace(go.Scatter(x=years, y=p50, mode='lines+markers',
                             line=dict(color=_AMBER, width=3),
                             marker=dict(size=4, color=_AMBER), name='P50 Cost'))
    fig.add_trace(go.Scatter(x=years, y=p10, mode='lines',
                             line=dict(color=_AMBER, width=1, dash='dot'), name='P10', opacity=0.7))

    fig.update_layout(title='Annual Intervention Cost — P10 / P50 / P90',
                      xaxis_title='Year', yaxis_title='Cost (USD millions)',
                      legend=dict(orientation='h', x=0, y=1.08))
    return _dark(fig, 420)


# ── Flagship: Risk Matrix ─────────────────────────────────────────────────────
def plot_risk_matrix(failure_prob_multiplier: float = 1.0) -> go.Figure:
    """
    5×5 risk matrix with component scatter positions.
    X-axis = Likelihood, Y-axis = Consequence.
    Multiplier shifts components rightward for higher-risk scenarios.
    """
    fig = go.Figure()

    # Background risk zone heatmap
    z = []
    for c in range(1, 6):
        row = []
        for l in range(1, 6):
            score = l * c
            row.append(0.1 if score <= 4 else 0.5 if score <= 9 else 0.9)
        z.append(row)

    fig.add_trace(go.Heatmap(
        z=z, x=[1, 2, 3, 4, 5], y=[1, 2, 3, 4, 5],
        colorscale=[
            [0.00, 'rgba(16,185,129,0.20)'],
            [0.35, 'rgba(16,185,129,0.20)'],
            [0.35, 'rgba(245,158,11,0.20)'],
            [0.65, 'rgba(245,158,11,0.20)'],
            [0.65, 'rgba(239,68,68,0.20)'],
            [1.00, 'rgba(239,68,68,0.20)'],
        ],
        showscale=False, hoverinfo='skip',
    ))

    # Component base positions: (likelihood, consequence, label, color)
    # Likelihood adjusted proportionally by scenario multiplier (capped at 5)
    _m = min(failure_prob_multiplier, 2.0)
    components = [
        (min(5.0, 3.2 * _m**0.4), 4.2, 'Tubing',       _RED),
        (min(5.0, 2.5 * _m**0.4), 4.0, 'Packer',       _ORANGE),
        (min(5.0, 1.8 * _m**0.4), 4.5, 'Casing',       _RED),
        (min(5.0, 1.5 * _m**0.4), 4.8, 'Cement',       _RED),
        (min(5.0, 4.0 * _m**0.25), 2.7, 'Wellhead',    _AMBER),
        (min(5.0, 4.8 * _m**0.2),  1.2, 'Gauge',       _GREEN),
        (min(5.0, 4.2 * _m**0.25), 2.2, 'Injectivity', _AMBER),
    ]

    for lk, cs, label, color in components:
        lk = max(1.0, lk)
        fig.add_trace(go.Scatter(
            x=[lk], y=[cs], mode='markers+text',
            marker=dict(size=20, color=color, opacity=0.85,
                        line=dict(color='#0f172a', width=2)),
            text=[label],
            textposition='top center',
            textfont=dict(size=9, color=color),
            name=label, showlegend=False,
            hovertemplate=(
                f'<b>{label}</b><br>Likelihood: {lk:.1f}/5<br>'
                f'Consequence: {cs:.1f}/5<extra></extra>'
            ),
        ))

    x_ticks = ['1 — Rare', '2 — Unlikely', '3 — Possible', '4 — Likely', '5 — Almost Certain']
    y_ticks = ['1 — Negligible', '2 — Minor', '3 — Moderate', '4 — Major', '5 — Catastrophic']

    fig.update_layout(
        title='Component Risk Matrix — Likelihood vs Consequence',
        xaxis=dict(title='Likelihood', range=[0.4, 5.6], tickvals=[1, 2, 3, 4, 5],
                   ticktext=x_ticks, tickangle=-15),
        yaxis=dict(title='Consequence', range=[0.4, 5.6], tickvals=[1, 2, 3, 4, 5],
                   ticktext=y_ticks),
    )
    for x, y, txt, col in [(1.2, 1.2, 'LOW RISK', _GREEN),
                            (2.8, 2.8, 'MEDIUM', _AMBER),
                            (4.5, 4.5, 'HIGH RISK', _RED)]:
        fig.add_annotation(x=x, y=y, text=txt, showarrow=False,
                           font=dict(color=col, size=9, family='Inter,sans-serif'),
                           opacity=0.5)
    return _dark(fig, 500)


# ── Bathtub Curve ─────────────────────────────────────────────────────────────
def plot_bathtub_curve(
    failure_df: pd.DataFrame,
    n_wells: int,
    n_simulations: int,
    operating_years: int,
) -> go.Figure:
    """
    Bathtub curve with three phase annotations and failure-mode callouts.
    Simulated failure rate is overlaid on the conceptual bathtub reference.
    """
    fig = go.Figure()
    if failure_df.empty:
        return _dark(fig)

    years = list(range(1, operating_years + 1))
    total = n_simulations * n_wells

    rates_raw = failure_df.groupby('year').size() / max(total, 1)
    actual = [float(rates_raw.get(yr, 0.0)) for yr in years]
    actual_s = pd.Series(actual).rolling(3, center=True, min_periods=1).mean().tolist()

    stable_base = float(np.mean(actual_s[4:min(10, len(actual_s))]) if len(actual_s) > 5 else 0.05)
    wear_start  = int(operating_years * 0.70)

    def bathtub_ref(t):
        infant  = stable_base * 1.5 * np.exp(-1.2 * t) + stable_base * 0.5 * np.exp(-0.3 * t)
        wearout = 0.0
        if t >= wear_start:
            frac = (t - wear_start) / max(operating_years - wear_start, 1)
            wearout = stable_base * frac ** 2 * 2.0
        return float(stable_base + infant + wearout)

    ref = [bathtub_ref(yr) for yr in years]

    # Phase shading
    fig.add_vrect(x0=0.5, x1=2.5,            fillcolor=_AMBER, opacity=0.08, line_width=0)
    fig.add_vrect(x0=2.5, x1=wear_start + 0.5, fillcolor=_GREEN, opacity=0.06, line_width=0)
    fig.add_vrect(x0=wear_start + 0.5, x1=operating_years + 0.5,
                  fillcolor=_RED, opacity=0.08, line_width=0)

    # Phase labels
    y_top = max(ref + actual_s) * 1.02
    for x_pos, label, sublabel, color in [
        (1.5,                                       'Infant Mortality',  'Installation defects · Commissioning', _AMBER),
        ((2.5 + wear_start) / 2,                    'Useful Life',       'Random · Uncorrelated failures',       _GREEN),
        ((wear_start + operating_years + 0.5) / 2,  'Wear-Out',          'Corrosion · Fatigue · Degradation',    _RED),
    ]:
        fig.add_annotation(x=x_pos, y=y_top, text=f'<b>{label}</b>',
                           showarrow=False, font=dict(color=color, size=9),
                           yanchor='bottom', opacity=0.9)
        fig.add_annotation(x=x_pos, y=y_top * 0.91, text=sublabel,
                           showarrow=False, font=dict(color=color, size=7),
                           yanchor='bottom', opacity=0.55)

    fig.add_trace(go.Scatter(x=years, y=ref, mode='lines',
                             line=dict(color=_AMBER, width=1.5, dash='dot'),
                             name='Bathtub Reference', opacity=0.55))
    fig.add_trace(go.Scatter(x=years, y=actual_s, mode='lines+markers',
                             line=dict(color=_BLUE, width=2.5),
                             marker=dict(size=4, color=_BLUE),
                             name='Simulated Rate (per well/yr)'))

    # Wear-out annotation arrow
    wo_y = actual_s[wear_start - 1] if wear_start <= len(actual_s) else y_top * 0.5
    fig.add_annotation(x=wear_start, y=wo_y, text='Wear-out begins',
                       arrowhead=2, arrowcolor=_RED, font=dict(color=_RED, size=8),
                       showarrow=True, ax=30, ay=-25)

    fig.update_layout(
        title='Reliability Lifecycle — Failure Rate by Phase',
        xaxis_title='Year', yaxis_title='Failures per Well per Year',
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
    )
    return _dark(fig, 420)


def plot_lifecycle_heatmap(heatmap_df: pd.DataFrame) -> go.Figure:
    """
    Component × Year failure probability heatmap (flagship visualisation).

    Rows = components ordered by barrier class (safety first).
    Columns = years.
    Values = adjusted annual failure probability at P50 MTTF.
    Colour = green (low) → amber → red (high).
    """
    fig = go.Figure()
    if heatmap_df.empty:
        return _dark(fig)

    # Order rows: safety barriers first, then production, flow_assurance, monitoring
    order = {'safety': 0, 'production': 1, 'flow_assurance': 2, 'monitoring': 3}
    heatmap_df = heatmap_df.copy()
    heatmap_df['_order'] = heatmap_df['barrier_class'].map(order).fillna(4)

    comps = (
        heatmap_df[['display_name', '_order']]
        .drop_duplicates()
        .sort_values('_order')['display_name']
        .tolist()
    )

    years = sorted(heatmap_df['year'].unique())
    # Build z matrix: rows=components, cols=years
    z = []
    for comp in comps:
        row_df = heatmap_df[heatmap_df['display_name'] == comp].set_index('year')
        row = [float(row_df.loc[yr, 'adjusted_prob']) if yr in row_df.index else 0.0
               for yr in years]
        z.append(row)

    fig.add_trace(go.Heatmap(
        z=z,
        x=years,
        y=comps,
        colorscale=[
            [0.0,  '#0f4c1a'],   # deep green (very low probability)
            [0.15, '#166534'],
            [0.35, '#854d0e'],   # amber
            [0.6,  '#c2410c'],   # orange
            [1.0,  '#7f1d1d'],   # deep red
        ],
        colorbar=dict(
            title=dict(text='Annual P(fail)', side='right',
                       font=dict(color='#94a3b8', size=9)),
            tickformat='.1%',
            len=0.85,
            thickness=12,
            bgcolor='rgba(0,0,0,0)',
            tickfont=dict(color='#94a3b8', size=9),
        ),
        hovertemplate=(
            '<b>%{y}</b><br>'
            'Year %{x}<br>'
            'Annual P(fail): %{z:.2%}<extra></extra>'
        ),
        xgap=1,
        ygap=1,
    ))

    # Barrier-class dividers (horizontal lines between groups)
    barrier_classes = [
        heatmap_df[heatmap_df['display_name'] == c]['barrier_class'].iloc[0]
        for c in comps
    ]
    for i in range(1, len(comps)):
        if barrier_classes[i] != barrier_classes[i - 1]:
            fig.add_shape(
                type='line', xref='paper', yref='y',
                x0=0, x1=1, y0=i - 0.5, y1=i - 0.5,
                line=dict(color='#334155', width=1.5),
            )

    fig.update_layout(
        title='Component Lifecycle Failure Probability Heatmap',
        xaxis_title='Year',
        yaxis_title=None,
        yaxis=dict(tickfont=dict(size=10, color='#cbd5e1')),
        xaxis=dict(tickfont=dict(size=9)),
        margin=dict(l=160, r=20, t=50, b=40),
    )
    return _dark(fig, 380)


# ── Lifecycle Forecast ────────────────────────────────────────────────────────
def plot_annual_workover_demand(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if df.empty:
        return _dark(fig)
    yr = df['year']
    _ribbon(fig, yr, df['p10_workovers'], df['p90_workovers'], _RED_A, 'P10–P90 Range')
    fig.add_trace(go.Scatter(x=yr, y=df['p50_workovers'], mode='lines+markers',
                             line=dict(color=_RED, width=2.5), marker=dict(size=4), name='P50'))
    fig.update_layout(title='Annual Workover Demand', xaxis_title='Year',
                      yaxis_title='Workovers per Year')
    return _dark(fig)


def plot_annual_intervention_demand(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if df.empty:
        return _dark(fig)
    yr = df['year']
    _ribbon(fig, yr, df['p10_interventions'], df['p90_interventions'], _BLUE_A, 'P10–P90 Range')
    fig.add_trace(go.Scatter(x=yr, y=df['p50_interventions'], mode='lines+markers',
                             line=dict(color=_BLUE, width=2.5), marker=dict(size=4), name='P50'))
    fig.update_layout(title='Annual Total Intervention Demand', xaxis_title='Year',
                      yaxis_title='Interventions per Year')
    return _dark(fig)


def plot_cumulative_workovers(failure_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if failure_df.empty:
        return _dark(fig)
    wo = failure_df[failure_df['intervention_type'] == 'full_workover']
    if wo.empty:
        return _dark(fig)
    cum = (wo.groupby(['simulation_id', 'year']).size()
             .groupby(level=0).cumsum().reset_index(name='cwo'))
    years = sorted(cum['year'].unique())
    p10 = [cum[cum['year'] == yr]['cwo'].quantile(0.10) for yr in years]
    p50 = [cum[cum['year'] == yr]['cwo'].quantile(0.50) for yr in years]
    p90 = [cum[cum['year'] == yr]['cwo'].quantile(0.90) for yr in years]
    _ribbon(fig, years, p10, p90, _RED_A, 'P10–P90 Range')
    fig.add_trace(go.Scatter(x=years, y=p50, mode='lines',
                             line=dict(color=_RED, width=2.5), name='P50'))
    fig.update_layout(title='Cumulative Workovers Over Time',
                      xaxis_title='Year', yaxis_title='Cumulative Workovers')
    return _dark(fig)


def plot_lifecycle_cost_distribution(annual_costs: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if annual_costs.empty:
        return _dark(fig)
    lc = annual_costs.groupby('simulation_id')['total_cost'].sum() / 1e6
    fig.add_trace(go.Histogram(x=lc, nbinsx=50, marker_color=_BLUE, opacity=0.7, name='Sims'))
    for pct, label, color in [(0.10, 'P10', _GREEN), (0.50, 'P50', _AMBER), (0.90, 'P90', _RED)]:
        val = lc.quantile(pct)
        fig.add_vline(x=val, line_dash='dash', line_color=color,
                      annotation_text=f'{label}: ${val:.0f}M',
                      annotation_font=dict(color=color, size=10))
    fig.update_layout(title='Lifecycle Cost Distribution',
                      xaxis_title='Total Cost (USD millions)', yaxis_title='Count')
    return _dark(fig)


# ── Failure Modes ─────────────────────────────────────────────────────────────
def plot_failure_by_component(failure_df: pd.DataFrame) -> go.Figure:
    if failure_df.empty:
        return _dark(go.Figure())
    counts = failure_df.groupby('component').size().sort_values().reset_index(name='count')
    fig = px.bar(counts, x='count', y='component', orientation='h',
                 color='count', color_continuous_scale=['#1e293b', _RED],
                 title='Total Failures by Component')
    fig.update_layout(coloraxis_showscale=False, xaxis_title='Failure Events (all simulations)',
                      yaxis_title='')
    return _dark(fig)


def plot_intervention_type_split(failure_df: pd.DataFrame) -> go.Figure:
    if failure_df.empty:
        return _dark(go.Figure())
    counts = failure_df.groupby('intervention_type').size().reset_index(name='count')
    colors = [_ITYPE.get(t, _SLATE) for t in counts['intervention_type']]
    fig = go.Figure(go.Pie(labels=counts['intervention_type'], values=counts['count'],
                            marker_colors=colors, hole=0.45,
                            textfont=dict(size=10)))
    fig.update_layout(title='Intervention Type Distribution',
                      legend=dict(font=dict(size=10)))
    return _dark(fig)


def plot_severity_distribution(failure_df: pd.DataFrame) -> go.Figure:
    if failure_df.empty:
        return _dark(go.Figure())
    counts = failure_df.groupby(['component', 'severity']).size().reset_index(name='count')
    fig = px.bar(counts, x='component', y='count', color='severity', barmode='stack',
                 color_discrete_map=_SEVERITY, title='Failure Severity by Component')
    fig.update_layout(xaxis_tickangle=-35, yaxis_title='Failure Events (all simulations)',
                      xaxis_title='')
    return _dark(fig)


def plot_cost_by_component(failure_df: pd.DataFrame) -> go.Figure:
    if failure_df.empty:
        return _dark(go.Figure())
    costs = (failure_df.groupby('component')['estimated_cost'].sum() / 1e6
             ).sort_values().reset_index()
    costs.columns = ['component', 'cost_m']
    fig = px.bar(costs, x='cost_m', y='component', orientation='h',
                 color='cost_m', color_continuous_scale=['#1e293b', _AMBER],
                 title='Intervention Cost by Component')
    fig.update_layout(coloraxis_showscale=False,
                      xaxis_title='Total Cost (USD millions)', yaxis_title='')
    return _dark(fig)


def plot_component_treemap(failure_df: pd.DataFrame) -> go.Figure:
    if failure_df.empty:
        return _dark(go.Figure())
    df = (failure_df.groupby(['severity', 'component'])
          .agg(total_cost=('estimated_cost', 'sum'),
               event_count=('simulation_id', 'count'))
          .reset_index())
    df['label'] = df['component'].str.replace('_', ' ').str.title()
    df['cost_m'] = df['total_cost'] / 1e6

    color_map = {'(?)': '#1e293b', 'All': '#1e293b',
                 'high': '#7f1d1d', 'medium': '#78350f', 'low': '#064e3b'}
    fig = px.treemap(df, path=[px.Constant('All'), 'severity', 'label'],
                     values='total_cost', color='severity',
                     color_discrete_map=color_map,
                     custom_data=['cost_m', 'event_count'],
                     title='Cost Contribution — Component Breakdown')
    fig.update_traces(
        texttemplate='<b>%{label}</b><br>$%{customdata[0]:.1f}M',
        hovertemplate='<b>%{label}</b><br>Cost: $%{customdata[0]:.1f}M<br>'
                      'Events: %{customdata[1]:,.0f}<extra></extra>',
        textfont=dict(size=11),
    )
    return _dark(fig, 480)


def plot_cost_waterfall(
    failure_df: pd.DataFrame,
    annual_costs: pd.DataFrame,
    n_simulations: int = 1,
) -> go.Figure:
    fig = go.Figure()
    if failure_df.empty:
        return _dark(fig)

    # Show P50 per-simulation costs (divide aggregate by number of simulations)
    n = max(n_simulations, 1)
    wo_cost  = failure_df[failure_df['intervention_type'] == 'full_workover']['estimated_cost'].sum() / n
    rl_cost  = failure_df[failure_df['intervention_type'] == 'rigless_intervention']['estimated_cost'].sum() / n
    li_cost  = failure_df[failure_df['intervention_type'] == 'light_intervention']['estimated_cost'].sum() / n
    mob_cost = (annual_costs['mobilisation_cost'].sum() if 'mobilisation_cost' in annual_costs.columns else 0) / n
    def_cost = (annual_costs['deferred_injection_cost'].sum() if 'deferred_injection_cost' in annual_costs.columns else 0) / n

    vals_m = [v / 1e6 for v in [wo_cost, rl_cost, li_cost, mob_cost, def_cost]]
    cats   = ['Full Workovers', 'Rigless', 'Light Interventions', 'Mob / Demob', 'Deferred Inj. Loss']
    total  = sum(vals_m)

    fig.add_trace(go.Waterfall(
        orientation='v',
        measure=['relative'] * len(vals_m) + ['total'],
        x=cats + ['Total'],
        y=vals_m + [0],
        connector=dict(line=dict(color='#334155', width=1)),
        increasing=dict(marker=dict(color=_RED, line=dict(color='#7f1d1d', width=1))),
        decreasing=dict(marker=dict(color=_GREEN)),
        totals=dict(marker=dict(color=_BLUE, line=dict(color='#1e40af', width=1))),
        text=[f'${v:.0f}M' for v in vals_m] + [f'${total:.0f}M'],
        textposition='outside',
        textfont=dict(size=10, color='#e2e8f0'),
    ))
    fig.update_layout(title='Lifecycle Cost Breakdown — Average per Simulation',
                      yaxis_title='Cost (USD millions)', showlegend=False,
                      waterfallgap=0.35)
    return _dark(fig, 400)


# ── Campaign Planning ─────────────────────────────────────────────────────────
def plot_campaign_gantt(campaign_log: pd.DataFrame, n_sample: int = 12) -> go.Figure:
    """
    Campaign schedule as a bubble chart: X=year, Y=simulation, size=wells in campaign.
    Serves as the primary scheduling / Gantt-style view.
    """
    fig = go.Figure()
    if campaign_log.empty:
        return _dark(fig)

    sample_sims = sorted(campaign_log['simulation_id'].unique())[:n_sample]
    df = campaign_log[campaign_log['simulation_id'].isin(sample_sims)].copy()
    df['sim_label'] = 'Simulation ' + df['simulation_id'].astype(str).str.zfill(3)

    for c_type, color in _CTYPE.items():
        sub = df[df['campaign_type'] == c_type]
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub['campaign_year'],
            y=sub['sim_label'],
            mode='markers',
            marker=dict(
                size=(sub['n_wells'].clip(1, 30) + 4) * 1.8,
                color=color,
                symbol='square',
                opacity=0.78,
                line=dict(color='rgba(0,0,0,0.25)', width=1),
            ),
            name=c_type.replace('_', ' ').title(),
            customdata=sub[['n_wells', 'total_campaign_cost', 'n_rig_workovers']].values,
            hovertemplate=(
                '<b>%{y}</b> — Year %{x}<br>'
                'Wells: %{customdata[0]:.0f}<br>'
                'Rig Workovers: %{customdata[2]:.0f}<br>'
                'Cost: $%{customdata[1]:,.0f}<extra></extra>'
            ),
        ))

    fig.update_layout(
        title='Campaign Schedule — Sample Simulations  (bubble size ∝ campaign size)',
        xaxis_title='Year', yaxis_title='',
        xaxis=dict(range=[0, df['campaign_year'].max() + 1]),
        legend=dict(orientation='h', x=0, y=1.1),
    )
    return _dark(fig, max(380, n_sample * 34))


def plot_campaign_timeline(campaign_log: pd.DataFrame) -> go.Figure:
    if campaign_log.empty:
        return _dark(go.Figure())
    counts = campaign_log.groupby('campaign_year').size().reset_index(name='n')
    rig_counts = (campaign_log[campaign_log['n_rig_workovers'] > 0]
                  .groupby('campaign_year').size().reset_index(name='n_rig'))
    merged = counts.merge(rig_counts, on='campaign_year', how='left').fillna(0)

    fig = go.Figure()
    fig.add_trace(go.Bar(x=merged['campaign_year'], y=merged['n'],
                         name='All Campaigns', marker_color=_BLUE, opacity=0.6))
    fig.add_trace(go.Bar(x=merged['campaign_year'], y=merged['n_rig'],
                         name='Rig Campaigns', marker_color=_RED, opacity=0.8))
    fig.update_layout(title='Campaign Activity by Year (All Simulations)',
                      barmode='overlay', xaxis_title='Year', yaxis_title='Campaign Count')
    return _dark(fig)


def plot_campaign_size_distribution(campaign_log: pd.DataFrame) -> go.Figure:
    if campaign_log.empty:
        return _dark(go.Figure())
    fig = px.histogram(campaign_log, x='n_wells', nbins=25,
                       color='campaign_type',
                       color_discrete_map=_CTYPE,
                       title='Campaign Size Distribution — Wells per Campaign',
                       barmode='stack')
    fig.update_layout(xaxis_title='Wells per Campaign', yaxis_title='Count')
    return _dark(fig)


def plot_deferred_queue_evolution(
    failure_df: pd.DataFrame,
    campaign_log: pd.DataFrame,
    operating_years: int,
) -> go.Figure:
    """
    Cumulative deferred interventions entering the queue per year.
    Vertical markers show when batch campaigns fired (clearing the queue).
    """
    fig = go.Figure()
    if failure_df.empty:
        return _dark(fig)

    deferred = failure_df[failure_df['immediate_or_deferred'] == 'deferred']
    if deferred.empty:
        return _dark(fig)

    years = list(range(1, operating_years + 1))
    all_sims = failure_df['simulation_id'].unique()

    pivot = (
        deferred.groupby(['simulation_id', 'year']).size()
        .unstack(fill_value=0)
        .reindex(index=all_sims, fill_value=0)
    )
    for yr in years:
        if yr not in pivot.columns:
            pivot[yr] = 0
    pivot = pivot[years]
    cum = pivot.cumsum(axis=1)

    p50 = [cum[yr].quantile(0.50) for yr in years]
    p90 = [cum[yr].quantile(0.90) for yr in years]

    _ribbon(fig, years, [0] * len(years), p90, _PURPLE_A, 'P50–P90 Queue Depth')
    fig.add_trace(go.Scatter(x=years, y=p50, mode='lines',
                             line=dict(color=_PURPLE, width=2.5), name='P50 Queue Depth'))

    # Mark batch campaign years
    if not campaign_log.empty:
        batch = campaign_log[campaign_log['campaign_type'] == 'deferred_batch']
        if not batch.empty:
            top_years = batch.groupby('campaign_year').size().nlargest(5).index
            for yr in top_years:
                fig.add_vline(x=yr, line_dash='dot', line_color=_BLUE, opacity=0.5,
                              annotation_text='Campaign', annotation_font_size=9,
                              annotation_font_color=_BLUE,
                              annotation_position='top right')

    fig.update_layout(
        title='Deferred Intervention Queue — Cumulative Depth',
        xaxis_title='Year',
        yaxis_title='Cumulative Deferred Events',
    )
    return _dark(fig)


def plot_deferred_queue(failure_df: pd.DataFrame, operating_years: int) -> go.Figure:
    if failure_df.empty:
        return _dark(go.Figure())
    deferred = failure_df[failure_df['immediate_or_deferred'] == 'deferred']
    if deferred.empty:
        return _dark(go.Figure())
    counts = deferred.groupby(['simulation_id', 'year']).size().reset_index(name='n')
    p50 = [counts[counts['year'] == yr]['n'].quantile(0.5)
           if yr in counts['year'].values else 0
           for yr in range(1, operating_years + 1)]
    fig = go.Figure(go.Bar(x=list(range(1, operating_years + 1)), y=p50,
                           marker_color=_PURPLE, opacity=0.75, name='P50 Deferred'))
    fig.update_layout(title='Deferred Interventions per Year (P50)',
                      xaxis_title='Year', yaxis_title='Events')
    return _dark(fig)


def plot_immediate_vs_deferred(failure_df: pd.DataFrame) -> go.Figure:
    if failure_df.empty:
        return _dark(go.Figure())
    counts = (failure_df.groupby(['year', 'immediate_or_deferred']).size()
              .reset_index(name='count'))
    fig = px.bar(counts, x='year', y='count', color='immediate_or_deferred',
                 barmode='stack',
                 color_discrete_map={'immediate': _RED, 'deferred': _PURPLE},
                 title='Immediate vs Deferred Interventions by Year')
    fig.update_layout(yaxis_title='Events', xaxis_title='Year')
    return _dark(fig)


# ── Scenario Comparison ───────────────────────────────────────────────────────
def plot_scenario_comparison(comparison_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if comparison_df.empty:
        return _dark(fig)
    for col, label, color in [('p50_lifecycle_cost', 'P50 Cost', _BLUE),
                               ('p90_lifecycle_cost', 'P90 Cost', _RED)]:
        if col in comparison_df.columns:
            fig.add_trace(go.Bar(x=comparison_df['scenario'],
                                 y=comparison_df[col] / 1e6,
                                 name=label, marker_color=color))
    fig.update_layout(title='Lifecycle Cost by Scenario (USD millions)',
                      xaxis_title='', yaxis_title='Cost (USD millions)', barmode='group')
    return _dark(fig)


def plot_scenario_workovers(comparison_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if comparison_df.empty:
        return _dark(fig)
    for col, label, color in [('p50_workovers', 'P50 Workovers', _GREEN),
                               ('p90_workovers', 'P90 Workovers', _AMBER)]:
        if col in comparison_df.columns:
            fig.add_trace(go.Bar(x=comparison_df['scenario'],
                                 y=comparison_df[col],
                                 name=label, marker_color=color))
    fig.update_layout(title='Total Workovers by Scenario',
                      xaxis_title='', yaxis_title='Workovers', barmode='group')
    return _dark(fig)
