import pandas as pd


def schedule_campaigns(
    failure_df: pd.DataFrame,
    cost_assumptions: dict,
    campaign_threshold: int = 5,
    max_deferral_years: int = 3,
    operating_years: int = 30,
) -> tuple[pd.DataFrame, pd.DataFrame]:
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

    Returns a tuple of (campaign_log, event_map) DataFrames.
    campaign_log has one row per campaign.
    event_map has one row per event, linking each event to its campaign.
    """
    if failure_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    all_campaigns = []
    all_event_assignments = []

    for sim_id, sim_df in failure_df.groupby('simulation_id'):
        campaigns, event_assignments = _process_simulation(
            sim_id, sim_df, cost_assumptions,
            campaign_threshold, max_deferral_years, operating_years,
        )
        all_campaigns.extend(campaigns)
        all_event_assignments.extend(event_assignments)

    campaign_log = pd.DataFrame(all_campaigns) if all_campaigns else pd.DataFrame()
    event_map = pd.DataFrame(all_event_assignments) if all_event_assignments else pd.DataFrame()
    return campaign_log, event_map


def _process_simulation(
    sim_id, sim_df, cost_assumptions,
    campaign_threshold, max_deferral_years, operating_years,
):
    mob_cost = cost_assumptions.get('rig_mobilisation', 2_000_000)
    defer_inj_cost = cost_assumptions.get('deferred_injection_cost', 50_000)

    campaigns = []
    event_assignments = []
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
                    camp_id = f'SIM{sim_id}_C{campaign_counter:04d}'
                    n_dw = len({e['well_id'] for e in queue})
                    campaigns.append(_batch_campaign(
                        sim_id, campaign_counter, year, 'emergency',
                        queue, mob_cost, defer_inj_cost,
                    ))
                    for e in queue:
                        event_assignments.append({
                            'simulation_id': sim_id, 'well_id': e['well_id'],
                            'fail_year': e['fail_year'], 'component': e.get('component', ''),
                            'campaign_id': camp_id, 'campaign_type': 'emergency',
                            'campaign_year': year, 'campaign_size': n_dw,
                        })

                if not urgent.empty:
                    campaign_counter += 1
                    queue = _events_to_queue(year, urgent)
                    camp_id = f'SIM{sim_id}_C{campaign_counter:04d}'
                    n_dw = len({e['well_id'] for e in queue})
                    campaigns.append(_batch_campaign(
                        sim_id, campaign_counter, year, 'immediate',
                        queue, mob_cost, defer_inj_cost,
                    ))
                    for e in queue:
                        event_assignments.append({
                            'simulation_id': sim_id, 'well_id': e['well_id'],
                            'fail_year': e['fail_year'], 'component': e.get('component', ''),
                            'campaign_id': camp_id, 'campaign_type': 'immediate',
                            'campaign_year': year, 'campaign_size': n_dw,
                        })

            for _, event in deferred_year.iterrows():
                deferred_queue.append({
                    'fail_year': year,
                    'well_id': event['well_id'],
                    'component': event.get('component', ''),
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
            camp_id = f'SIM{sim_id}_C{campaign_counter:04d}'
            n_dw = len({e['well_id'] for e in deferred_queue})
            batch = _batch_campaign(
                sim_id, campaign_counter, year,
                'deferred_batch', deferred_queue,
                mob_cost, defer_inj_cost,
            )
            campaigns.append(batch)
            for e in deferred_queue:
                event_assignments.append({
                    'simulation_id': sim_id, 'well_id': e['well_id'],
                    'fail_year': e['fail_year'], 'component': e.get('component', ''),
                    'campaign_id': camp_id, 'campaign_type': 'deferred_batch',
                    'campaign_year': year, 'campaign_size': n_dw,
                })
            deferred_queue = []

    # Flush remaining deferred events at end of lifecycle
    if deferred_queue:
        campaign_counter += 1
        camp_id = f'SIM{sim_id}_C{campaign_counter:04d}'
        n_dw = len({e['well_id'] for e in deferred_queue})
        batch = _batch_campaign(
            sim_id, campaign_counter, operating_years,
            'end_of_life', deferred_queue,
            mob_cost, defer_inj_cost,
        )
        campaigns.append(batch)
        for e in deferred_queue:
            event_assignments.append({
                'simulation_id': sim_id, 'well_id': e['well_id'],
                'fail_year': e['fail_year'], 'component': e.get('component', ''),
                'campaign_id': camp_id, 'campaign_type': 'end_of_life',
                'campaign_year': operating_years, 'campaign_size': n_dw,
            })

    return campaigns, event_assignments


def _events_to_queue(year: int, events_df: pd.DataFrame) -> list[dict]:
    return [
        {
            'fail_year': year,
            'well_id': ev['well_id'],
            'component': ev.get('component', ''),
            'intervention_type': ev['intervention_type'],
            'cost': ev['estimated_cost'],
            'duration': ev['estimated_duration_days'],
        }
        for _, ev in events_df.iterrows()
    ]


def _batch_campaign(sim_id, counter, year, c_type, queue, mob_cost, defer_inj_cost):
    rig_events     = [e for e in queue if e['intervention_type'] == 'full_workover']
    rigless_events = [e for e in queue if e['intervention_type'] != 'full_workover']

    total_dur      = sum(e['duration'] for e in queue)
    total_int_cost = sum(e['cost'] for e in queue)

    mob = mob_cost if rig_events else 0.0
    defer_c = sum(
        (year - e['fail_year']) * 365.0 * defer_inj_cost
        for e in queue if e['intervention_type'] == 'full_workover'
    )

    # n_wells = distinct wells in this campaign; n_events = total component interventions
    # (a single well visit can address multiple components)
    n_distinct_wells = len({e['well_id'] for e in queue})

    return {
        'simulation_id': sim_id,
        'campaign_id': f'SIM{sim_id}_C{counter:04d}',
        'campaign_year': year,
        'campaign_type': c_type,
        'n_wells': n_distinct_wells,
        'n_events': len(queue),
        'n_rig_workovers': len(rig_events),
        'n_rigless': len(rigless_events),
        'total_duration_days': total_dur,
        'mobilisation_cost': mob,
        'intervention_cost': total_int_cost,
        'total_campaign_cost': mob + total_int_cost,
        'deferred_injection_cost': defer_c,
    }
