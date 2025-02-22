from dataclasses import dataclass
from zoneinfo import ZoneInfo
from typing import List, Dict, Optional
import datetime
from datetime import timedelta, datetime, date
import numpy as np
import pandas as pd
from pandas import MultiIndex
import requests
import random
import streamlit as st
import keyring
import time
import api_keys
import SolarPlatform
import csv

SOLAREDGE_BASE_URL = 'https://monitoringapi.solaredge.com/v2'
SOLAREDGE_SITE_URL = 'https://monitoring.solaredge.com/solaredge-web/p/site/'

@dataclass(frozen=True)
class SolarEdgeKeys:
    account_key : str
    api_key : str

def fetch_solaredge_keys():
    try:
        account_key = keyring.get_password("solaredge", "account_key")
        api_key = keyring.get_password("solaredge", "api_key")

        if any(key is None for key in [account_key, api_key]):
            raise ValueError("Missing SolarEdge key(s) in keyring.")

        return SolarEdgeKeys(account_key, api_key)
    
    except Exception as e:
        print(f"Error fetching SolarEdge keys: {e}")
        return None
    
#SOLAREDGE_KEYS = fetch_solaredge_keys()

SOLAREDGE_SLEEP = 0.2

SOLAREDGE_KEYS = SolarEdgeKeys(api_keys.SOLAREDGE_V2_ACCOUNT_KEY, api_keys.SOLAREDGE_V2_API_KEY)

SOLAREDGE_HEADERS = {
        "X-API-Key": SOLAREDGE_KEYS.api_key, 
        "Accept": "application/json",
        "X-Account-Key": SOLAREDGE_KEYS.account_key,
    }

class SolarEdgePlatform(SolarPlatform.SolarPlatform):
    @classmethod
    def get_vendorcode(cls):
        return "SE"

    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_WEEK)
    def get_sites_list(cls):
        url = f'{SOLAREDGE_BASE_URL}/sites'
        params = {"page": 1, "sites-in-page": 500}
        all_sites = []

        while True:
            cls.log("Fetching all sites from SolarEdge API...")
            response = requests.get(url, headers=SOLAREDGE_HEADERS, params=params)
            response.raise_for_status()
            sites = response.json()

            for site in sites:
                all_sites.append(site)

            if len(sites) < params["sites-in-page"]:
                break
            params["page"] += 1
        return all_sites

    @classmethod
    def get_sites_map(cls) -> Dict[str, SolarPlatform.SiteInfo]:
        sites = cls.get_sites_list()

        sites_dict = {}

        for site in sites:
            raw_site_id = site.get('siteId')
            inverters = cls.get_inverters(raw_site_id)
            #Skip sites with no inverters
            if inverters == []:
                continue
            site_url = SOLAREDGE_SITE_URL + str(raw_site_id)
            site_id = cls.add_vendorcodeprefix(raw_site_id)
            zipcode = site['location']['zip']
            name = site.get('name')
            latitude, longitude = SolarPlatform.get_coordinates(zipcode)
            site_info = SolarPlatform.SiteInfo(site_id, name, site_url, zipcode, latitude, longitude)
            sites_dict[site_id] = site_info

        return sites_dict

    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_MONTH())
    def get_devices(cls, raw_site_id):
        url = f'{SOLAREDGE_BASE_URL}/sites/{raw_site_id}/devices'
        params = {"types": ["BATTERY", "INVERTER"]}

        cls.log(f"Fetching Inverter / battery inventory data from SolarEdge API for site {raw_site_id}.")
        time.sleep(SOLAREDGE_SLEEP)
        response = requests.get(url, headers=SOLAREDGE_HEADERS, params=params)
        response.raise_for_status()
        devices = response.json()
        return devices 
    

    #Sort by created_time so that the order is stable.
    @classmethod
    def get_inverters(cls, raw_site_id):
        devices = cls.get_devices(raw_site_id)

        inverters = [device for device in devices if device.get('type') == 'INVERTER' and device.get('active') == True]
        sorted_data = sorted(inverters, key=lambda x: x['createdAt'])
        return sorted_data


    @classmethod
    def get_batteries(cls, raw_site_id):
        devices = cls.get_devices(raw_site_id)

        batteries = [device for device in devices if device.get('type') == 'BATTERY'  and device.get('active') == True]
        return batteries


    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_HOUR * 2)
    def get_battery_state_of_energy(cls, raw_site_id, serial_number):
        end_time = datetime.utcnow() #Fixme
        start_time = end_time - timedelta(minutes=15)

        url = f'{SOLAREDGE_BASE_URL}/sites/{raw_site_id}/storage/{serial_number}/state-of-energy'
        params = {'from': start_time.isoformat() + 'Z', 'to': end_time.isoformat() + 'Z',
                  'resolution': 'QUARTER_HOUR', 'unit': 'PERCENTAGE'}
        
        time.sleep(SOLAREDGE_SLEEP)
        cls.log(f"Fetching battery State of Energy from SolarEdge API for site {raw_site_id} and battery {serial_number}.")
        response = requests.get(url, headers=SOLAREDGE_HEADERS, params=params)
        response.raise_for_status()
        soe_data = response.json().get('values', [])

        latest_value = next((entry['value'] for entry in reversed(
            soe_data) if entry['value'] is not None), None)
        return latest_value

    @classmethod
    def get_batteries_soe(cls, site_id):
        raw_site_id = cls.strip_vendorcodeprefix(site_id)

        batteries = cls.get_batteries(raw_site_id)
        battery_states = []

        for battery in batteries:
            serial_number = battery.get('serialNumber')
            soe = cls.get_battery_state_of_energy(raw_site_id, serial_number)
            soe_pct = soe * 100 if soe is not None else 0

            battery_states.append({'serialNumber': serial_number, 'model': battery.get(
                'model'), 'stateOfEnergy': soe_pct})

        return battery_states

    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_WEEK)
    def _get_inverter_production(cls, raw_site_id, reference_time, inverter_id):
        formatted_begin_time = reference_time.isoformat(timespec='seconds').replace('+00:00', 'Z')
        end_time = reference_time + timedelta(minutes=15)
        formatted_end_time = end_time.isoformat(timespec='seconds').replace('+00:00', 'Z')

        url = SOLAREDGE_BASE_URL + f'/sites/{raw_site_id}/inverters/{inverter_id}/power'
        params = {'from': formatted_begin_time , 'to': formatted_end_time,
                  'resolution': 'QUARTER_HOUR', 'unit': 'KW'}

        cls.log(f"Fetching production from SolarEdge API for site: {raw_site_id} inverter: {inverter_id} at {formatted_begin_time}.")
        time.sleep(SOLAREDGE_SLEEP)
        response = requests.get(url, headers=SOLAREDGE_HEADERS, params=params)
        response.raise_for_status()
        json = response.json().get('values', [])
        return json


    @classmethod
    def get_inverter_production(cls, raw_site_id, reference_time, inverter_id):
        powers = cls._get_inverter_production(raw_site_id, reference_time, inverter_id)
        power = powers[0].get('value', 0.0)
        if power is None:
            power = 0.0

        power = round(power, 2)
        return power

    @classmethod
    def get_production(cls, site_id, reference_time) -> List[float]:
        raw_site_id = cls.strip_vendorcodeprefix(site_id)
        inverters = cls.get_inverters(raw_site_id)

        productions = []
        for inverter in inverters:
            serial_number = inverter.get('serialNumber')
            power = cls.get_inverter_production(raw_site_id, reference_time, serial_number)
            productions.append(power)

        return productions
    

    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_WEEK)
    def _get_site_energy(cls, raw_site_id, start_date, end_date):
        # Get local timezone from cache, defaulting to SolarPlatform.DEFAULT_TIMEZONE
        tz = ZoneInfo(SolarPlatform.cache.get('TimeZone', SolarPlatform.DEFAULT_TIMEZONE))
        
        # Convert dates to 6 AM local start and 23:59:59 local end, then to UTC
        start_local = datetime.combine(start_date, datetime.time(6, 0, 0), tzinfo=tz)
        end_local = datetime.combine(end_date, datetime.time(23, 59, 59), tzinfo=tz)
        start_utc = start_local.astimezone(datetime.timezone.utc)
        end_utc = end_local.astimezone(datetime.timezone.utc)

        # Format as ISO 8601 with seconds precision and Z
        formatted_start = start_utc.isoformat(timespec='seconds').replace('+00:00', 'Z')
        formatted_end = end_utc.isoformat(timespec='seconds').replace('+00:00', 'Z')
        
        # Construct API URL and parameters
        url = SOLAREDGE_BASE_URL + f'/sites/{raw_site_id}/energy'
        params = {
            'from': formatted_start,
            'to': formatted_end,
            'resolution': 'DAY'
        }
        
        # Log the exact URL for debugging
        full_url = requests.Request('GET', url, headers=SOLAREDGE_HEADERS, params=params).prepare().url
        cls.log(f"Fetching energy from SolarEdge API for site: {raw_site_id} with URL: {full_url}")
        time.sleep(1) #Longer sleep for this expensive request, but not all day because we have a lot to gather ;-)
    
        # Make API request with retries
        for attempt in range(3):
            try:
                response = requests.get(url, headers=SOLAREDGE_HEADERS, params=params)
                response.raise_for_status()
                # Validate response data before returning to avoid caching bad data
                json_data = response.json()
                values = json_data.get('values', [])
                if not values:
                    cls.log(f"Empty data returned for site {raw_site_id} from {formatted_start} to {formatted_end}")
                return values  # Only return if successful and valid
            except Exception as e:
                cls.log(f"Attempt {attempt+1} failed for site {raw_site_id}: {e}")
                if attempt == 2:  # Last attempt
                    raise  # Rethrow after 3 failures
                time.sleep(5)  # Wait before retrying
    

    @classmethod
    def save_site_yearly_production(cls, year: int, site_ids: Optional[List[str]] = None) -> str:
        sites_map = cls.get_sites_map()
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
            raw_site_id = cls.strip_vendorcodeprefix(site_id)
            
        error_msg = None
    
        for start_date, end_date in intervals:
            try:
                energy_data = cls._get_site_energy(raw_site_id, start_date, end_date)
                if energy_data and (energy_data[0]['timestamp'].split('T')[0] != start_date.strftime('%Y-%m-%d') or energy_data[-1]['timestamp'].split('T')[0] != end_date.strftime('%Y-%m-%d')):
                    cls.log(f"Warning: Data range mismatch for site {raw_site_id}: requested {start_date} to {end_date}, got {energy_data[0]['timestamp']} to {energy_data[-1]['timestamp']}")
            except Exception as e:
                error_msg = f"Error for site {raw_site_id} from {start_date} to {end_date}: {str(e)}"
                cls.log(error_msg)
                break  # Stop processing this site and move to saving

            if not energy_data:
                cls.log(f"No data returned for site {raw_site_id} from {start_date} to {end_date}")
            else:
                cls.log(f"Returned {len(energy_data)} items for site {raw_site_id} from {start_date} to {end_date}")

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

        prefix = cls.get_vendorcode()
        dynamic_file_name = f"{prefix}_production_{year}_{file_suffix}.csv"

        if error_msg:
            # Add a row with the error message at the end of the DataFrame
            error_row = pd.Series(index=df.columns, dtype='object')
            error_row[:] = error_msg
            f = pd.concat([df, error_row.to_frame().T], ignore_index=False)
            
        df.to_csv(dynamic_file_name, index_label='Date')
        return dynamic_file_name


    @classmethod
    def convert_alert_to_standard(cls, alert):
        if alert == "SITE_COMMUNICATION_FAULT":
            return SolarPlatform.AlertType.NO_COMMUNICATION
        if alert == "INVERTER_BELOW_THRESHOLD_LIMIT":
            return SolarPlatform.AlertType.PRODUCTION_ERROR
        if alert == "PANEL_COMMUNICATION_FAULT":
            return SolarPlatform.AlertType.PANEL_ERROR
        else:
            return SolarPlatform.AlertType.CONFIG_ERROR

    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_HOUR * 2)
    def get_alerts(cls) -> List[SolarPlatform.SolarAlert]:
        url = f'{SOLAREDGE_BASE_URL}/alerts'
        all_alerts = []

        try:
            response = requests.get(url, headers=SOLAREDGE_HEADERS)
            response.raise_for_status()
            alerts = response.json()
            for alert in alerts:
                # Filter out unwanted alert types
                if alert.get('type') == 'SNOW_ON_SITE':
                    continue

                site_id = cls.add_vendorcodeprefix(alert.get('siteId'))

                alert_type = cls.convert_alert_to_standard(alert.get('type'))
                alert_details = ''
                if alert_type == SolarPlatform.AlertType.CONFIG_ERROR:
                    alert_details = alert.get('type')

                first_triggered_str = alert.get('firstTrigger')
                # If the timestamp ends with a 'Z', replace it with '+00:00' for proper parsing
                if first_triggered_str and first_triggered_str.endswith("Z"):
                    first_triggered = datetime.fromisoformat(
                        first_triggered_str.replace("Z", "+00:00"))
                else:
                    first_triggered = first_triggered_str

                solarAlert = SolarPlatform.SolarAlert(site_id, alert_type, alert.get('impact'), alert_details, first_triggered)
                all_alerts.append(solarAlert)

            return all_alerts
        except requests.exceptions.RequestException as e:
            print(f"Failed to retrieve SolarEdge alerts: {e}")
            return []
