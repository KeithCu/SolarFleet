from zoneinfo import ZoneInfo
from datetime import datetime, timedelta, time, date
from typing import List, Optional, Tuple
import threading
import time as pytime
import os

from pandas import MultiIndex
import pandas as pd

import streamlit as st
import SolarPlatform
import Database as db

DUMP_DIRECTORY = "exports"

def get_year_intervals(year: int) -> List[Tuple[date, date]]:
    start_of_year = date(year, 1, 1)
    end_of_year = date(year, 12, 31)
    interval = timedelta(days=80)
    intervals = []
    current_start = start_of_year
    
    while current_start <= end_of_year:
        current_end = min(current_start + interval - timedelta(days=1), end_of_year)
        intervals.append((current_start, current_end))
        current_start = current_end + timedelta(days=1)
    
    return intervals

def validate_data_range(platform, site_id, energy_data, start_date, end_date):
    if not energy_data:
        return False

    first_str = energy_data[0]['timestamp'].split('T')[0]
    last_str = energy_data[-1]['timestamp'].split('T')[0]
    first_returned = date.fromisoformat(first_str)
    last_returned = date.fromisoformat(last_str)

    if first_returned > start_date or last_returned < end_date:
        platform.log(f"Insufficient data for site {site_id}: requested {start_date} to {end_date}, got {first_returned} to {last_returned}")
        return False

    if first_returned < start_date or last_returned > end_date:
        platform.log(f"Warning: Extra data for site {site_id}: requested {start_date} to {end_date}, got {first_returned} to {last_returned}")

    return True

def process_energy_data(data_dict, energy_data, site_id):
    """Process energy data into the data dictionary"""
    for item in energy_data:
        date_str = item['timestamp'].split('T')[0]
        value = item['value']
        if date_str not in data_dict:
            data_dict[date_str] = {}
        data_dict[date_str][site_id] = value

def merge_site_files(file_list, output_file):
    """Merge individual site CSV files into one combined file"""
    dataframes = []
    
    for file in file_list:
        if file and os.path.exists(file):
            site_df = pd.read_csv(file, index_col=0)
            dataframes.append(site_df)
    
    if dataframes:
        # Merge all dataframes by their date index
        result = pd.concat(dataframes, axis=1)
        result.to_csv(output_file, index_label='Date')

def process_single_site(platform, year: int, site_id: str, sites_map: dict) -> Optional[str]:
    """Process a single site with retry logic and save to individual file"""
    site_name = sites_map[site_id].name if site_id in sites_map else site_id
    site_code = site_id.split(':')[1] if ':' in site_id else site_id
    prefix = platform.get_vendorcode()
    site_file = os.path.join(DUMP_DIRECTORY, f"{prefix}_{site_code}_{year}_temp.csv")
    
    data = {}
    site_errors = []
    
    intervals = get_year_intervals(year)
    
    # Process each interval with retries
    for start_date, end_date in intervals:
        max_retries = 3
        retry_count = 0
        success = False
        
        while not success and retry_count < max_retries:
            try:
                energy_data = platform.get_site_energy(site_id, start_date, end_date)
                if energy_data:  # non-empty list; may be partial
                    if not validate_data_range(platform, site_id, energy_data, start_date, end_date):
                        platform.log(f"Partial data for {site_id} from {start_date} to {end_date}")
                    process_energy_data(data, energy_data, site_id)
                    success = True
                else:
                    platform.log(f"No data for {site_id} from {start_date} to {end_date} (site may not be installed yet)")
                    success = True
            except Exception as e:
                error_msg = f"Error for site {site_id} from {start_date} to {end_date}: {str(e)}"
                platform.log(error_msg)
                site_errors.append(error_msg)
                retry_count += 1
                if retry_count < max_retries:
                    platform.log(f"Retrying ({retry_count}/{max_retries})...")
                    pytime.sleep(2 ** retry_count)  # Exponential backoff
    
    # Always create file even if no data was collected
    dates = pd.date_range(start=date(year, 1, 1), end=date(year, 12, 31), freq='D').strftime('%Y-%m-%d').tolist()
    if data:
        df = pd.DataFrame.from_dict(data, orient='index')
        df = df.reindex(index=dates, fill_value=0.0)
    else:
        df = pd.DataFrame(0.0, index=dates, columns=[f"{site_name} ({site_id})"])
    df.columns = MultiIndex.from_tuples([(f"{site_name} ({site_id})", 'Production - Energy (WH)')])
    
    if site_errors:
        error_info = pd.DataFrame({"Errors": site_errors})
        error_info.to_csv(site_file.replace('.csv', '_errors.csv'), index=False)
        # Also add each error as a row in the main DataFrame
        for error_msg in site_errors:
            error_row = pd.Series(index=df.columns, dtype='object')
            error_row[:] = error_msg
            df = pd.concat([df, error_row.to_frame().T], ignore_index=True)
            
    df.to_csv(site_file, index_label='Date')
    return site_file


def save_site_yearly_production(platform, year: int, site_ids: Optional[List[str]] = None) -> List[str]:
    sites_map = platform.get_sites_map()
    if site_ids is None:
        site_ids = sorted(sites_map.keys())
        file_suffix = "All_Sites"
    else:
        file_suffix = f"{site_ids[0].split(':')[1]}_et_al" if len(site_ids) > 5 else "_".join([id.split(":")[1] for id in site_ids])
    
    # Keep track of successfully processed sites and generated files
    successful_files = []
    all_site_files = []
    
    # Process each site independently
    for site_id in site_ids:
        site_file = process_single_site(platform, year, site_id, sites_map)
        all_site_files.append(site_file)
        if site_file:  # None would indicate failed processing
            successful_files.append(site_file)
            
    # Merge all successful site files into final output
    if successful_files:
        prefix = platform.get_vendorcode()
        output_file = os.path.join(DUMP_DIRECTORY, f"{prefix}_production_{year}_{file_suffix}.csv")
        merge_site_files(successful_files, output_file)
        
        # Clean up individual site files if desired
        # for file in all_site_files:
        #     if file and os.path.exists(file):
        #         os.remove(file)
                
        return output_file
    return None


# The list of all platforms to collect data from
from SolarEdge import SolarEdgePlatform
from Enphase import EnphasePlatform
# from SolArk import SolArkPlatform
# from Solis import SolisPlatform

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