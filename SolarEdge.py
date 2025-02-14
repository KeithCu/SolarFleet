from typing import List, Dict
from datetime import datetime, timedelta
import requests
import random
import streamlit as st

import keyring
import SolarPlatform

SOLAREDGE_BASE_URL = 'https://monitoringapi.solaredge.com/v2'
SOLAREDGE_SITE_URL = 'https://monitoring.solaredge.com/solaredge-web/p/site/'

def fetch_solaredge_keys():
    """Fetches SolarEdge API keys from the keyring."""
    try:
        account_key = keyring.get_password("solaredge", "account_key")
        api_key = keyring.get_password("solaredge", "api_key")

        if any(key is None for key in [account_key, api_key]):
            raise ValueError("Missing SolarEdge key(s) in keyring.")

        return {
            "account_key": account_key,
            "api_key": api_key,
        }
    except Exception as e:
        print(f"Error fetching SolarEdge keys: {e}")
        return None
    
solaredge_keys = fetch_solaredge_keys()

SOLAREDGE_HEADERS = {
        "X-API-Key": solaredge_keys["api_key"],
        "Accept": "application/json",
        "X-Account-Key": solaredge_keys["account_key"],
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
            response = requests.get(
                url, headers=SOLAREDGE_HEADERS, params=params)
            response.raise_for_status()
            sites = response.json()

            for site in sites:
                all_sites.append(site)

            if len(sites) < params["sites-in-page"]:
                break
            params["page"] += 1
        return all_sites

    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_HOUR)
    def get_sites_map(cls) -> Dict[str, SolarPlatform.SiteInfo]:
        sites = cls.get_sites_list()

        sites_dict = {}

        for site in sites:
            site_url = SOLAREDGE_SITE_URL + str(site.get('siteId'))
            site_id = cls.add_vendorcodeprefix(site.get('siteId'))
            zipcode = site['location']['zip']
            name = site.get('name')
            if SolarPlatform.FAKE_DATA:
                name = str(random.randint(1000, 9999)) + " Main St"

            latitude, longitude = SolarPlatform.get_coordinates(zipcode)
            site_info = SolarPlatform.SiteInfo(
                site_id, name, site_url, zipcode, latitude, longitude)
            sites_dict[site_id] = site_info

        return sites_dict

    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_MONTH())
    def get_batteries(cls, raw_site_id):
        url = f'{SOLAREDGE_BASE_URL}/sites/{raw_site_id}/devices'
        params = {"types": ["BATTERY"]}

        cls.log(f"Fetching site / battery inventory data from SolarEdge API for site {raw_site_id}.")
        response = requests.get(url, headers=SOLAREDGE_HEADERS, params=params)
        response.raise_for_status()
        devices = response.json()

        batteries = [device for device in devices if device.get('type') == 'BATTERY']
        return batteries

    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_HOUR * 2)
    def get_battery_state_of_energy(cls, raw_site_id, serial_number):
        end_time = datetime.utcnow()
        start_time = datetime.utcnow() - timedelta(minutes=15)

        url = f'{SOLAREDGE_BASE_URL}/sites/{raw_site_id}/storage/{serial_number}/state-of-energy'
        params = {'from': start_time.isoformat() + 'Z', 'to': end_time.isoformat() + 'Z',
                  'resolution': 'QUARTER_HOUR', 'unit': 'PERCENTAGE'}

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

            battery_states.append({'serialNumber': serial_number, 'model': battery.get(
                'model'), 'stateOfEnergy': soe})

        return battery_states

    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_WEEK)
    def get_production(cls, site_id, reference_time):
        raw_site_id = cls.strip_vendorcodeprefix(site_id)

        end_time = reference_time + timedelta(minutes=15)
        url = SOLAREDGE_BASE_URL + f'/sites/{raw_site_id}/power'
        params = {'from': reference_time.isoformat() + 'Z', 'to': end_time.isoformat() + 'Z',
                  'resolution': 'QUARTER_HOUR', 'unit': 'KW'}

        cls.log(f"Fetching production data from SolarEdge API for site {raw_site_id} at {reference_time}.")

        response = requests.get(url, headers=SOLAREDGE_HEADERS, params=params)
        response.raise_for_status()
        power = response.json().get('values', [])

        latest_value = power[0].get('value', 0)
        return latest_value

    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_HOUR * 2)
    def get_alerts(cls) -> List[SolarPlatform.SolarAlert]:
        url = f'{SOLAREDGE_BASE_URL}/alerts'
        sites_dict = cls.get_sites_map()
        all_alerts = []

        try:
            response = requests.get(url, headers=SOLAREDGE_HEADERS)
            response.raise_for_status()
            alerts = response.json()
            for alert in alerts:
                site_id = cls.add_vendorcodeprefix(alert.get('siteId'))
                alert_details = ''  # FIXME
                first_triggered_str = alert.get('firstTrigger')
                # If the timestamp ends with a 'Z', replace it with '+00:00' for proper parsing
                if first_triggered_str and first_triggered_str.endswith("Z"):
                    first_triggered = datetime.fromisoformat(
                        first_triggered_str.replace("Z", "+00:00"))
                else:
                    first_triggered = first_triggered_str
                solarAlert = SolarPlatform.SolarAlert(site_id, alert.get(
                    'type'), alert.get('impact'), alert_details, first_triggered)
                all_alerts.append(solarAlert)

            return all_alerts
        except requests.exceptions.RequestException as e:
            print(f"Failed to retrieve SolarEdge alerts: {e}")
            return []
