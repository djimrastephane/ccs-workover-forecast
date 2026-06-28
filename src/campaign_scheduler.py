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

    Immediate interventions are grouped by year rather than one-per-event:
      - Emergency (reactive safety-barrier failures): one campaign per year
        grouping all emergency events in that year together.
      - Urgent (other immediate — escalated production failures): one campaign
        per year grouping all urgent events together.

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
    deferred_queue: list[dict] = []

    by_year: dict = {yr: grp for yr, grp in sim_df.groupby('year')}

    for year in range(1, operating_years + 1):
        year_df = by_year.get(year)

        if year_df is not None:
            immediate_df = year_df[year_df['immediate_or_deferred'] == 'immediate']
            deferred_year = year_df[year_df['immediate_or_deferred'] == 'deferred']

            if not immediate_df.empty:
                # Emergency: reactive safety-barrier failures — highest urgency,
                # but all in the same year can share one mobilisation.
                emergency = immediate_df[
                    (immediate_df['barrier_class'] == 'safety') &
                    (immediate_df['trigger_type'] == 'reactive')
                ]
                # Urgent: all other immediate events (escalated production, etc.)
                urgent = immediate_df[
                    ~(
                        (immediate_df['barrier_class'] == 'safety') &
                        (immediate_df['trigger_type'] == 'reactive')
                    )
                ]

                if not emergency.empty:
                    campaign_counter += 1
                    queue = _events_to_queue(year, emergency)
                    campaigns.append(_batch_campaign(
                        sim_id, campaign_counter, year, 'emergency',
                        queue, mob_cost, defer_inj_cost,
                    ))

                if not urgent.empty:
                    campaign_counter += 1
                    queue = _events_to_queue(year, urgent)
                    campaigns.append(_batch_campaign(
                        sim_id, campaign_counter, year, 'immediate',
                        queue, mob_cost, defer_inj_cost,
                    ))

            for _, event in deferred_year.iterrows():
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

    # Flush remaining deferred events at end of lifecycle
    if deferred_queue:
        campaign_counter += 1
        batch = _batch_campaign(
            sim_id, campaign_counter, operating_years,
            'end_of_life', deferred_queue,
            mob_cost, defer_inj_cost,
        )
        campaigns.append(batch)

    return campaigns


def _events_to_queue(year: int, events_df: pd.DataFrame) -> list[dict]:
    return [
        {
            'fail_year': year,
            'intervention_type': ev['intervention_type'],
            'cost': ev['estimated_cost'],
            'duration': ev['estimated_duration_days'],
        }
        for _, ev in events_df.iterrows()
    ]


def _batch_campaign(sim_id, counter, year, c_type, queue, mob_cost, defer_inj_cost):
    rig_events = [e for e in queue if e['intervention_type'] == 'full_workover']
    rigless_events = [e for e in queue if e['intervention_type'] != 'full_workover']

    total_dur = sum(e['duration'] for e in queue)
    total_int_cost = sum(e['cost'] for e in queue)

    mob = mob_cost if rig_events else 0.0
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
