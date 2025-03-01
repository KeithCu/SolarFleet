from zoneinfo import ZoneInfo
from datetime import datetime, timedelta, time, date
from typing import List, Optional
import threading
import time as pytime

from pandas import MultiIndex
import pandas as pd

import streamlit as st
import SolarPlatform
import Database as db


# The list of all platforms to collect data from
from SolarEdge import SolarEdgePlatform
from Enphase import EnphasePlatform
# from SolArk import SolArkPlatform
# from Solis import SolisPlatform

def save_site_yearly_production(platform, year: int, site_ids: Optional[List[str]] = None) -> str:
    sites_map = platform.get_sites_map()
    if site_ids is None:
        site_ids = sorted(sites_map.keys())
        file_suffix = "All_Sites"
    else:
        if len(site_ids) <= 5:
            file_suffix = "_".join([id.split(":")[1] for id in site_ids])
        else:
            file_suffix = f"{site_ids[0].split(':')[1]}_et_al"
    
    data = {}

    start_of_year = date(year, 1, 1)
    end_of_year = date(year, 12, 31)
    interval = timedelta(days=80)
    intervals = []
    current_start = start_of_year
    while current_start <= end_of_year:
        current_end = min(current_start + interval - timedelta(days=1), end_of_year)
        intervals.append((current_start, current_end))
        current_start = current_end + timedelta(days=1)

    for site_id in site_ids:        
        error_msg = None

        for start_date, end_date in intervals:
            try:
                energy_data = platform.get_site_energy(site_id, start_date, end_date)
                if energy_data and (energy_data[0]['timestamp'].split('T')[0] != start_date.strftime('%Y-%m-%d') or energy_data[-1]['timestamp'].split('T')[0] != end_date.strftime('%Y-%m-%d')):
                    platform.log(f"Warning: Data range mismatch for site {site_id}: requested {start_date} to {end_date}, got {energy_data[0]['timestamp']} to {energy_data[-1]['timestamp']}")
            except Exception as e:
                error_msg = f"Error for site {site_id} from {start_date} to {end_date}: {str(e)}"
                platform.log(error_msg)
                break  # Stop processing this site and move to saving

            if not energy_data:
                platform.log(f"No data returned for site {site_id} from {start_date} to {end_date}")
            else:
                platform.log(f"Returned {len(energy_data)} items for site {site_id} from {start_date} to {end_date}")

            for item in energy_data:
                date_str = item['timestamp'].split('T')[0]
                value = item['value']
                if date_str not in data:
                    data[date_str] = {}
                data[date_str][site_id] = value
    
            if error_msg:
                break  # Stop processing further sites if an error occurred

    start_date = date(year, 1, 1)
    end_date = date(year, 12, 31)
    dates = pd.date_range(start=start_date, end=end_date, freq='D').strftime('%Y-%m-%d').tolist()
    
    df = pd.DataFrame.from_dict(data, orient='index')        
    df = df.reindex(index=dates, columns=site_ids, fill_value=0.0)
    
    columns = [(f"{sites_map[site_id].name} ({site_id})", 'Production - Energy (WH)') for site_id in site_ids]
    df.columns = MultiIndex.from_tuples(columns)

    prefix = platform.get_vendorcode()
    dynamic_file_name = f"{prefix}_production_{year}_{file_suffix}.csv"

    if error_msg:
        # Add a row with the error message at the end of the DataFrame
        error_row = pd.Series(index=df.columns, dtype='object')
        error_row[:] = error_msg
        f = pd.concat([df, error_row.to_frame().T], ignore_index=False)
        
    df.to_csv(dynamic_file_name, index_label='Date')
    return dynamic_file_name

def get_recent_noon() -> datetime:
    now = SolarPlatform.get_now()
    tz = ZoneInfo(SolarPlatform.cache.get('TimeZone', SolarPlatform.DEFAULT_TIMEZONE))
    today = now.date()

    threshold = datetime.combine(today, time(12, 30), tzinfo=tz)  # Threshold in specified tz

    measurement_date = today if now >= threshold else today - timedelta(days=1)

    noon_local = datetime.combine(measurement_date, time(12, 0), tzinfo=tz) # Noon in specified tz
    noon_utc = noon_local.astimezone(ZoneInfo("UTC")) # Convert to UTC

    return noon_utc

def collect_platform(platform):
    sites = None
    platform.log("Starting collection at " + str(datetime.now()))
    production_set = set()
    reference_date = get_recent_noon()
    sites = platform.get_sites_map()

    try:
        for site_id in sites.keys():
            db.add_site_if_not_exists(site_id)

            battery_data = platform.get_batteries_soe(site_id)
            for battery in battery_data:
                db.update_battery_data(site_id, battery['serialNumber'], battery['model'], battery['stateOfEnergy'])

            # Fetch production data and put into set
            site_production_dict = platform.get_production(site_id, reference_date)

            if site_production_dict is not None:
                new_production = SolarPlatform.ProductionRecord(
                    site_id = site_id,
                    production_kw = site_production_dict,
                )
                production_set.add(new_production)

        platform.log("Data collection complete")
        # Add production data to database
        db.process_bulk_solar_production(reference_date, production_set, False, 3.0)

        SolarPlatform.cache['collection_status'][platform.get_vendorcode()] = 'completed'

    except Exception as e:
        platform.log(f"Error while fetching sites: {e}")
        return

    try:
        alerts = platform.get_alerts()
        for alert in alerts:
            db.add_alert_if_not_exists(alert.site_id, str(alert.alert_type), alert.details, alert.severity, alert.first_triggered)

    except Exception as e:
        platform.log(f"Error while fetching alerts: {e}")
        return

def run_collection():
    # Initialize the collection status
    SolarPlatform.cache['collection_running'] = True
    SolarPlatform.cache['collection_completed'] = False
    SolarPlatform.cache['collection_status'] = {}

    # Start threads for each platform
    threads = []
    for platform_class in SolarPlatform.SolarPlatform.__subclasses__():
        platform_instance = platform_class()
        thread = threading.Thread(target=collect_platform, args=(platform_instance,))
        threads.append(thread)
        thread.start()

    # Process logs and wait for all threads to finish
    while any(thread.is_alive() for thread in threads):
        # Display logs from the queue
        while not SolarPlatform.SolarPlatform.collection_queue.empty():
            log_message = SolarPlatform.SolarPlatform.collection_queue.get()
            st.write(log_message)
            SolarPlatform.SolarPlatform.collection_queue.task_done()
        pytime.sleep(0.1)  # Small sleep to prevent tight loop

    # All threads are done
    SolarPlatform.cache['collection_running'] = False
    SolarPlatform.cache['collection_completed'] = True