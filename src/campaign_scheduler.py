import pandas as pd


def schedule_campaigns(
    failure_df: pd.DataFrame,
    cost_assumptions: dict,
    campaign_threshold: int = 5,
    max_deferral_years: int = 3,
    operating_years: int = 30,
) -> pd.DataFrame:
    """
    Convert intervention decisions into campaign batches.

    Immediate interventions trigger their own campaign (emergency mobilisation).
    Deferred interventions accumulate in a queue and trigger a batch campaign when:
      - Queue size reaches campaign_threshold, OR
      - Oldest queued item has waited max_deferral_years

    Returns a campaign_log DataFrame with one row per campaign.
    """
    if failure_df.empty:
        return pd.DataFrame()

    all_campaigns = []

    for sim_id, sim_df in failure_df.groupby('simulation_id'):
        campaigns = _process_simulation(
            sim_id, sim_df, cost_assumptions,
            campaign_threshold, max_deferral_years, operating_years,
        )
        all_campaigns.extend(campaigns)

    return pd.DataFrame(all_campaigns) if all_campaigns else pd.DataFrame()


def _process_simulation(
    sim_id, sim_df, cost_assumptions,
    campaign_threshold, max_deferral_years, operating_years,
):
    mob_cost = cost_assumptions.get('rig_mobilisation', 2_000_000)
    defer_inj_cost = cost_assumptions.get('deferred_injection_cost', 50_000)

    campaigns = []
    campaign_counter = 0
    # Each item: {'fail_year': int, 'intervention_type': str, 'cost': float, 'duration': float}
    deferred_queue: list[dict] = []

    # Pre-group by year so the inner loop is O(1)
    by_year: dict = {yr: grp for yr, grp in sim_df.groupby('year')}

    for year in range(1, operating_years + 1):
        year_df = by_year.get(year)

        if year_df is not None:
            immediate = year_df[year_df['immediate_or_deferred'] == 'immediate']
            for _, event in immediate.iterrows():
                campaign_counter += 1
                is_rig = event['intervention_type'] == 'full_workover'
                barrier_class = (
                    event['barrier_class']
                    if 'barrier_class' in event.index
                    else 'production'
                )
                c_type_actual = 'emergency' if barrier_class == 'safety' else 'immediate'
                campaigns.append(_single_campaign(
                    sim_id, campaign_counter, year,
                    c_type_actual, event, mob_cost, is_rig,
                ))

            for _, event in year_df[year_df['immediate_or_deferred'] == 'deferred'].iterrows():
                deferred_queue.append({
                    'fail_year': year,
                    'intervention_type': event['intervention_type'],
                    'cost': event['estimated_cost'],
                    'duration': event['estimated_duration_days'],
                })

        # Trigger a batch campaign if threshold or max-age is reached
        should_flush = (
            len(deferred_queue) >= campaign_threshold
            or (deferred_queue and (year - deferred_queue[0]['fail_year']) >= max_deferral_years)
        )

        if should_flush and deferred_queue:
            campaign_counter += 1
            batch = _batch_campaign(
                sim_id, campaign_counter, year,
                'deferred_batch', deferred_queue,
                mob_cost, defer_inj_cost,
            )
            campaigns.append(batch)
            deferred_queue = []

    # Flush any remaining deferred events at end of lifecycle
    if deferred_queue:
        campaign_counter += 1
        batch = _batch_campaign(
            sim_id, campaign_counter, operating_years,
            'end_of_life', deferred_queue,
            mob_cost, defer_inj_cost,
        )
        campaigns.append(batch)

    return campaigns


def _single_campaign(sim_id, counter, year, c_type, event, mob_cost, is_rig):
    mob = mob_cost if is_rig else 0.0
    return {
        'simulation_id': sim_id,
        'campaign_id': f'SIM{sim_id}_C{counter:04d}',
        'campaign_year': year,
        'campaign_type': c_type,
        'n_wells': 1,
        'n_rig_workovers': int(is_rig),
        'n_rigless': int(not is_rig),
        'total_duration_days': event['estimated_duration_days'],
        'mobilisation_cost': mob,
        'intervention_cost': event['estimated_cost'],
        'total_campaign_cost': mob + event['estimated_cost'],
        'deferred_injection_cost': 0.0,
    }


def _batch_campaign(sim_id, counter, year, c_type, queue, mob_cost, defer_inj_cost):
    rig_events = [e for e in queue if e['intervention_type'] == 'full_workover']
    rigless_events = [e for e in queue if e['intervention_type'] != 'full_workover']

    total_dur = sum(e['duration'] for e in queue)
    total_int_cost = sum(e['cost'] for e in queue)

    mob = mob_cost if rig_events else 0.0
    # Deferred injection penalty: sum of each rig workover's wait (years→days) × daily cost
    defer_c = sum(
        (year - e['fail_year']) * 365.0 * defer_inj_cost
        for e in queue if e['intervention_type'] == 'full_workover'
    )

    return {
        'simulation_id': sim_id,
        'campaign_id': f'SIM{sim_id}_C{counter:04d}',
        'campaign_year': year,
        'campaign_type': c_type,
        'n_wells': len(queue),
        'n_rig_workovers': len(rig_events),
        'n_rigless': len(rigless_events),
        'total_duration_days': total_dur,
        'mobilisation_cost': mob,
        'intervention_cost': total_int_cost,
        'total_campaign_cost': mob + total_int_cost,
        'deferred_injection_cost': defer_c,
    }
