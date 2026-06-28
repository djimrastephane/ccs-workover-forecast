"""Model QA and sanity check engine."""
import pandas as pd
import numpy as np


def compute_qa_metrics(failure_df, campaign_log, lifecycle_summary, params):
    n_wells = params.get('n_wells', 1)
    operating_years = params.get('operating_years', 30)
    n_simulations = params.get('n_simulations', 1)
    metrics = {}
    if failure_df.empty:
        return metrics

    wo_df = failure_df[failure_df['intervention_type'] == 'full_workover']
    wo_rate = wo_df.shape[0] / max(n_simulations * n_wells * operating_years, 1)
    metrics['workovers_per_well'] = {
        'value': round(wo_rate, 4), 'unit': 'per well-year',
        'label': 'Full Workover Rate',
        'norm': (0.02, 0.08),
        'description': 'Annual full workover demand per well, averaged across all simulations and years',
    }

    if not campaign_log.empty:
        camps_per_year = len(campaign_log) / max(n_simulations * operating_years, 1)
        metrics['campaigns_per_year'] = {
            'value': round(camps_per_year, 3), 'unit': 'per year (avg simulation)',
            'label': 'Campaign Frequency',
            'norm': (1.0, 8.0),
            'description': 'Average campaigns per year per simulation — high values suggest excessive mobilisations',
        }

        avg_size = campaign_log['n_wells'].mean()
        metrics['avg_wells_per_campaign'] = {
            'value': round(avg_size, 2), 'unit': 'wells/campaign',
            'label': 'Average Campaign Size',
            'norm': (2.0, 10.0),
            'description': 'Average wells per campaign — very small campaigns are economically inefficient',
        }

        imm_count = campaign_log[campaign_log['campaign_type'].isin(['immediate', 'emergency'])].shape[0]
        imm_frac = imm_count / max(len(campaign_log), 1)
        metrics['immediate_fraction'] = {
            'value': round(imm_frac, 3), 'unit': 'fraction',
            'label': 'Immediate Intervention Fraction',
            'norm': (0.0, 0.60),
            'description': 'Fraction of campaigns that are immediate — high values imply frequent safety failures',
        }

        emg_count = campaign_log[campaign_log['campaign_type'] == 'emergency'].shape[0]
        emg_frac = emg_count / max(len(campaign_log), 1)
        metrics['emergency_fraction'] = {
            'value': round(emg_frac, 3), 'unit': 'fraction',
            'label': 'Emergency Campaign Fraction',
            'norm': (0.0, 0.35),
            'description': 'Fraction triggered by safety barrier failures — >35% is implausible for a maintained asset',
        }

    comp_counts = failure_df.groupby('component').size()

    cement_n = comp_counts.get('cement_barrier', 0)
    tubing_n = comp_counts.get('tubing', 0)
    if tubing_n > 0:
        metrics['cement_vs_tubing_ratio'] = {
            'value': round(cement_n / tubing_n, 3), 'unit': 'ratio',
            'label': 'Cement / Tubing Event Ratio',
            'norm': (0.0, 0.8),
            'description': 'Cement failures should be rarer than tubing failures; ratio >1 is unrealistic within 30 years',
        }

    if 'barrier_class' in failure_df.columns:
        mon_n = failure_df[failure_df['barrier_class'] == 'monitoring'].shape[0]
        prod_n = failure_df[failure_df['barrier_class'] == 'production'].shape[0]
        if prod_n > 0:
            metrics['monitoring_vs_production_ratio'] = {
                'value': round(mon_n / prod_n, 3), 'unit': 'ratio',
                'label': 'Monitoring / Production Event Ratio',
                'norm': (0.5, 4.0),
                'description': 'Monitoring components fail frequently but cheaply; ratio <0.5 suggests under-representation',
            }

    return metrics


def generate_qa_warnings(metrics, params):
    warnings = []
    n_wells = params.get('n_wells', 1)
    campaign_threshold = params.get('campaign_threshold', 5)

    wo_rate = metrics.get('workovers_per_well', {}).get('value', 0)
    if wo_rate > 0.10:
        warnings.append({
            'severity': 'critical', 'metric': 'workovers_per_well',
            'value': f'{wo_rate:.4f}/well-year',
            'message': (f'Full workover rate ({wo_rate:.4f}/well-year) is very high. '
                        f'CCS industry expectation is <0.05/well-year. '
                        f'Review packer and tubing MTTF assumptions.'),
            'reference': 'SPE-232388-MS: 0.02–0.08 workovers/well/year for maintained CCS assets',
        })
    elif wo_rate > 0.05:
        warnings.append({
            'severity': 'warning', 'metric': 'workovers_per_well',
            'value': f'{wo_rate:.4f}/well-year',
            'message': (f'Full workover rate ({wo_rate:.4f}/well-year) is above typical CCS expectations. '
                        f'Verify MTTF assumptions reflect asset-specific integrity management.'),
            'reference': 'Expected: 0.02–0.05/well-year for maintained offshore CCS wells',
        })

    camps_yr = metrics.get('campaigns_per_year', {}).get('value', 0)
    if camps_yr > 10:
        warnings.append({
            'severity': 'critical', 'metric': 'campaigns_per_year',
            'value': f'{camps_yr:.1f}/year',
            'message': (f'Campaign frequency ({camps_yr:.1f}/year) is implausibly high for an offshore asset '
                        f'with {n_wells} wells and threshold={campaign_threshold}. '
                        f'Check for excessive safety barrier failures bypassing the deferred queue.'),
            'reference': 'Typical offshore CCS: 2–8 campaigns/year for assets >50 wells',
        })
    elif camps_yr > 6:
        warnings.append({
            'severity': 'warning', 'metric': 'campaigns_per_year',
            'value': f'{camps_yr:.1f}/year',
            'message': (f'Campaign frequency ({camps_yr:.1f}/year) is elevated. '
                        f'Consider increasing campaign threshold to consolidate operations.'),
            'reference': 'Typical offshore: 2–6 campaigns/year',
        })

    avg_size = metrics.get('avg_wells_per_campaign', {}).get('value', 0)
    if avg_size < 1.5:
        warnings.append({
            'severity': 'warning', 'metric': 'avg_wells_per_campaign',
            'value': f'{avg_size:.2f} wells/campaign',
            'message': (f'Average campaign size ({avg_size:.2f} wells) is very small — most campaigns are '
                        f'single-well emergency mobilisations. This is economically inefficient and may '
                        f'indicate overly conservative intervention thresholds.'),
            'reference': 'Economic batching typically requires ≥3 wells per campaign',
        })

    imm_frac = metrics.get('immediate_fraction', {}).get('value', 0)
    if imm_frac > 0.70:
        warnings.append({
            'severity': 'critical', 'metric': 'immediate_fraction',
            'value': f'{imm_frac*100:.0f}% immediate',
            'message': (f'{imm_frac*100:.0f}% of campaigns are immediate. The deferred batching logic is '
                        f'rarely triggering, which implies very high failure rates or a safety-barrier-dominated portfolio.'),
            'reference': 'Industry expectation: <60% immediate interventions for a batch-planned asset',
        })

    emg_frac = metrics.get('emergency_fraction', {}).get('value', 0)
    if emg_frac > 0.35:
        warnings.append({
            'severity': 'warning', 'metric': 'emergency_fraction',
            'value': f'{emg_frac*100:.0f}% emergency',
            'message': (f'{emg_frac*100:.0f}% of campaigns are emergency (safety-critical). High emergency rates '
                        f'imply frequent cement/casing barrier failures — review their MTTF assumptions.'),
            'reference': 'Emergency campaigns should represent <35% of total mobilisations',
        })

    ct_ratio = metrics.get('cement_vs_tubing_ratio', {}).get('value', 0)
    if ct_ratio > 1.0:
        warnings.append({
            'severity': 'warning', 'metric': 'cement_vs_tubing_ratio',
            'value': f'{ct_ratio:.2f}',
            'message': (f'Cement barrier events ({ct_ratio:.2f}×) exceed tubing events. Cement failures are '
                        f'typically rarer than tubing failures for CO2 injection wells within 30 years. '
                        f'Review cement MTTF assumptions.'),
            'reference': 'NORSOK D-010: tubing failures typically 2–5× more frequent than cement failures',
        })

    if not warnings:
        warnings.append({
            'severity': 'pass', 'metric': 'all', 'value': 'Pass',
            'message': ('All validation metrics are within expected ranges. '
                        'The model is producing results consistent with CCS well integrity literature.'),
            'reference': 'See Assumption Quality Register for individual assumption confidence levels',
        })

    return warnings
