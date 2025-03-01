from enum import Enum
import time
import requests
import base64
import keyring
from datetime import datetime
from dataclasses import dataclass
from typing import Dict, List

import SolarPlatform

ENPHASE_BASE_URL = "https://api.enphaseenergy.com"
ENPHASE_TOKENS = "Enphase Tokens"
ENPHASE_SITE_URL = "https://enlighten.enphaseenergy.com/systems/"


@dataclass(frozen=True)
class EnphaseKeys:
    client_id: str
    client_secret: str
    api_key: str
    user_email: str
    user_password: str

def fetch_enphase_keys():
    client_id = keyring.get_password("enphase", "client_id")
    client_secret = keyring.get_password("enphase", "client_secret")
    api_key = keyring.get_password("enphase", "api_key")
    user_email = keyring.get_password("enphase", "user_email")
    user_password = keyring.get_password("enphase", "user_password")

    if any(key is None for key in [client_id, client_secret, api_key, user_email, user_password]):
        raise ValueError("Missing Enphase key(s) in keyring.")

    return EnphaseKeys(client_id=client_id, client_secret=client_secret, api_key=api_key, user_email=user_email, user_password=user_password,
    )

import api_keys

#Enphase Installer API has 300 requests per minute, so add a small amount of sleeps to the API to prevent errors.
#200 ms is probably overkill, since each request usually takes 1 second, but it is friendly to have some pauses.
ENPHASE_SLEEP = 0.2

ENPHASE_KEYS = EnphaseKeys(client_id=api_keys.ENPHASE_CLIENT_ID, client_secret=api_keys.ENPHASE_CLIENT_SECRET,
                            api_key=api_keys.ENPHASE_API_KEY, user_email=api_keys.ENPHASE_USER_EMAIL,
                            user_password=api_keys.ENPHASE_USER_PASSWORD)

#ENPHASE_KEYS = fetch_enphase_keys()

class EnphasePlatform(SolarPlatform.SolarPlatform):

    @classmethod
    def get_vendorcode(cls):
        return "EN"

    @staticmethod
    def get_basic_auth_header(client_id, client_secret):
        credentials = f"{client_id}:{client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        return {"Authorization": f"Basic {encoded_credentials}"}

    @classmethod
    def authenticate_enphase(cls, username, password, refresh_token=None):
        url = f"{ENPHASE_BASE_URL}/oauth/token"

        if refresh_token:
            data = {"grant_type": "refresh_token", "refresh_token": refresh_token}
        else:
            data = {"grant_type": "password", "username": username, "password": password}

        headers = EnphasePlatform.get_basic_auth_header(ENPHASE_KEYS.client_id, ENPHASE_KEYS.client_secret)
        try:
            cls.log("Trying to Authenticate with Enphase API.")
            response = requests.post(url, data=data, headers=headers)
            response.raise_for_status()
            tokens = response.json()
            expires_in = tokens.get("expires_in", 3600)
            return tokens.get("access_token"), tokens.get("refresh_token"), expires_in
        except requests.exceptions.RequestException as e:
            cls.log(f"Authentication failed: {e}")
            return None, None, None

    @classmethod
    def get_access_token(cls):
        current_time = int(time.time())
        tokens = SolarPlatform.cache.get(ENPHASE_TOKENS)
        if tokens:
            stored_access_token, stored_refresh_token, expires_at = tokens
            if current_time < expires_at:
                return stored_access_token
            
        access_token, new_refresh_token, expires_in = cls.authenticate_enphase(ENPHASE_KEYS.user_email, ENPHASE_KEYS.user_password)
        if access_token:
            expires_at = current_time + expires_in
            SolarPlatform.cache.set(ENPHASE_TOKENS, (access_token, new_refresh_token,
                                    expires_at), expire=SolarPlatform.CACHE_EXPIRE_YEAR)
            return access_token
        else:
            cls.log("Authentication failed in get_access_token")
            return None

    #We use this to check for alerts, so cache for a short period of time.
    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_HOUR * 4)
    def get_sites_list(cls) -> list:
        access_token = cls.get_access_token()
        if not access_token:
            return []

        all_systems = []
        page = 1
        size = 503  # Fetch many sites instead of the default 10.

        while True:
            url = f"{ENPHASE_BASE_URL}/api/v4/systems?key={ENPHASE_KEYS.api_key}&size={size}&page={page}"
            headers = {"Authorization": f"Bearer {access_token}"}
            try:
                cls.log(f"Fetching sites from Enphase API, page: {page}.")
                response = requests.get(url, headers=headers)
                response.raise_for_status()
                raw_data = response.json()
                systems_page = raw_data.get("systems", [])
                all_systems.extend(systems_page)
                if len(systems_page) < size:
                    break
                page += 1
            except requests.exceptions.RequestException as e:
                cls.log(f"Failed to retrieve Enphase systems raw data for page {page}: {e}")
                break
        return all_systems

    @classmethod
    def get_sites_map(cls) -> Dict[str, SolarPlatform.SiteInfo]:
        raw_systems_data = cls.get_sites_list()
        sites_dict = {}
        for system in raw_systems_data:
            raw_system_id = system.get("system_id")
            site_id = cls.add_vendorcodeprefix(raw_system_id)
            name = system.get("name", f"System {raw_system_id}")
            location = system.get("location", {})
            zipcode = location.get("zip", "48071")
            latitude, longitude = SolarPlatform.get_coordinates(zipcode)
            site_url = ENPHASE_SITE_URL + str(raw_system_id)
            site_info = SolarPlatform.SiteInfo(site_id, name, site_url, zipcode, latitude, longitude)
            sites_dict[site_id] = site_info
        return sites_dict

    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_WEEK)
    def get_production_micros(cls, site_id, reference_time) -> float:
        epoch_time = int(reference_time.timestamp())
        access_token = cls.get_access_token()
        if not access_token:
            return 0.0
        raw_system_id = cls.strip_vendorcodeprefix(site_id)
        url = f"{ENPHASE_BASE_URL}/api/v4/systems/{raw_system_id}/telemetry/production_micro?key={ENPHASE_KEYS.api_key}&start_at={epoch_time}&granularity=15mins"
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            time.sleep(ENPHASE_SLEEP)
            cls.log(f"Fetching production data from Enphase API for system {raw_system_id} at {reference_time}.")
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data
        except requests.exceptions.RequestException as e:
            cls.log(
                f"Failed to retrieve production data for system {raw_system_id}: {e}")
            return 0.0

    #Enphase currently only has one production value per site.
    @classmethod
    def get_production(cls, site_id, reference_time) -> Dict[str, float]:
        json = cls.get_production_micros(site_id, reference_time)
        values = json.get("intervals", [])
        for entry in reversed(values):
            latest_value = entry.get("powr", 0.0)
            return {"ALL" : latest_value / 1000.0}
        return {"ALL" : 0.0}

    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.cache_expire_month())
    def get_site_devices(cls, raw_system_id) -> dict:
        access_token = cls.get_access_token()
        if not access_token:
            return []
        url = f"{ENPHASE_BASE_URL}/api/v4/systems/{raw_system_id}/devices?key={ENPHASE_KEYS.api_key}"
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            time.sleep(ENPHASE_SLEEP)
            cls.log(f"Fetching devices from Enphase API for system {raw_system_id} (metadata).")
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            json = response.json()
            return json
        except requests.exceptions.RequestException as e:
            cls.log(f"Failed to retrieve devices for system {raw_system_id}: {e}")
            return []

    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_WEEK)
    def get_site_energy(cls, site_id, start_date, end_date):
        pass

    @classmethod
    def get_batteries_metadata(cls, raw_system_id) -> list:
        json = cls.get_site_devices(raw_system_id)
        devices = json.get("devices", [])

        battery_devices = []
        for device in devices:
            if "encharges" in device:
                encharges = devices["encharges"]
                for encharge in encharges:
                    battery_devices.append(encharge)  # Add the device to the list

        return battery_devices

    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_DAY)
    def get_battery_state_of_energy(cls, raw_system_id, serial_number):
        access_token = cls.get_access_token()
        if not access_token:
            return None
        url = f"{ENPHASE_BASE_URL}/api/v4/systems/{raw_system_id}/devices/encharges/{serial_number}/telemetry?key={ENPHASE_KEYS.api_key}"
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            time.sleep(ENPHASE_SLEEP)
            cls.log(f"Fetching battery telemetry for Enphase system {raw_system_id}, battery {serial_number}.")
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            json = response.json()
            return json
        except requests.exceptions.RequestException as e:
            cls.log(f"Failed to retrieve telemetry for battery {serial_number} in system {raw_system_id}: {e}")
            return None

    @classmethod
    def strip_trailing_digits(cls, s):
        i = len(s) - 1
        while s[i].isdigit():
            i -= 1
        return s[:i].strip()
    
    @classmethod
    def get_batteries_soe(cls, site_id) -> list:
        raw_system_id = cls.strip_vendorcodeprefix(site_id)
        batteries = cls.get_batteries_metadata(raw_system_id)
        battery_states = []
        for battery in batteries:
            serial_number = battery.get("serial_number")
            model = cls.strip_trailing_digits(battery.get("name"))
            json = cls.get_battery_state_of_energy(raw_system_id, serial_number)
            if json is None:
                soe = 0.0
            else:
                soe = json["intervals"][0]["soc"]["percent"]

            battery_states.append({
                "serialNumber": serial_number,
                "model": model,
                "stateOfEnergy": soe
            })
        return battery_states

    @classmethod
    def convert_alert_to_standard(cls, alert):
        if alert == "comm":
            return SolarPlatform.AlertType.NO_COMMUNICATION
        if alert == "power":
            return SolarPlatform.AlertType.PRODUCTION_ERROR
        if alert == "micro":
            return SolarPlatform.AlertType.PANEL_ERROR
        else:
            return SolarPlatform.AlertType.CONFIG_ERROR

    # get_sites_list() caches so use and adjust that one instead.
    @classmethod
    def get_alerts(cls) -> list:
        sites = cls.get_sites_list()
        alerts = []
        for site in sites:
            status = site.get("status", "normal").lower()
            if status != "normal":
                raw_system_id = site.get("system_id")
                site_id = cls.add_vendorcodeprefix(raw_system_id)
                alert_type = cls.convert_alert_to_standard(status)
                details = ""
                if alert_type == SolarPlatform.AlertType.CONFIG_ERROR:
                    details = status
                severity = 50  # FIXME Adjust severity
                 # FIXME Look for this data, at least for comms errors.
                first_triggered = SolarPlatform.get_now()
                alert = SolarPlatform.SolarAlert(site_id, alert_type, severity, details, first_triggered)
                alerts.append(alert)
        return alerts
