from dataclasses import dataclass
from typing import List, Dict
from datetime import datetime, timedelta
import numpy as np
import requests
import random
import streamlit as st
import keyring
import time
import api_keys
import SolarPlatform

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
            if SolarPlatform.FAKE_DATA:
                name = str(random.randint(1000, 9999)) + " Main St"

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
        end_time = datetime.utcnow()
        start_time = datetime.utcnow() - timedelta(minutes=15)

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

        cls.log(f"Fetching production from SolarEdge API for site: {raw_site_id} inverter: {inverter_id} at {reference_time}.")
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
