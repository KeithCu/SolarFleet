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
    """Fetches Enphase API keys from the keyring and returns an EnphaseKeys dataclass.
       Raises ValueError if any keys are missing.
    """
    client_id = keyring.get_password("enphase", "client_id")
    client_secret = keyring.get_password("enphase", "client_secret")
    api_key = keyring.get_password("enphase", "api_key")
    user_email = keyring.get_password("enphase", "user_email")
    user_password = keyring.get_password("enphase", "user_password")

    if any(key is None for key in [client_id, client_secret, api_key, user_email, user_password]):
        raise ValueError("Missing Enphase key(s) in keyring.")

    return EnphaseKeys(
        client_id=client_id,
        client_secret=client_secret,
        api_key=api_key,
        user_email=user_email,
        user_password=user_password,
    )

import api_keys

ENPHASE_KEYS = EnphaseKeys(client_id=api_keys.ENPHASE_CLIENT_ID, client_secret=api_keys.ENPHASE_CLIENT_SECRET,
                            api_key=api_keys.ENPHASE_API_KEY, user_email=api_keys.ENPHASE_USER_EMAIL,
                            user_password=api_keys.ENPHASE_USER_PASSWORD)

#ENPHASE_KEYS = fetch_enphase_keys()
    
# Shared standard error codes across vendors.

class StandardErrorCodes(Enum):
    NO_COMMUNICATION = "NO_COMMUNICATION"
    CONFIG_ERROR = "CONFIG_ERROR"
    HARDWARE_ERROR = "HARDWARE_ERROR"
    API_ERROR = "API_ERROR"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


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
            data = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token
            }
        else:
            data = {
                "grant_type": "password",
                "username": username,
                "password": password
            }
        headers = EnphasePlatform.get_basic_auth_header(
            ENPHASE_KEYS.client_id, ENPHASE_KEYS.client_secret)
        try:
            response = requests.post(url, data=data, headers=headers)
            response.raise_for_status()
            tokens = response.json()
            expires_in = tokens.get("expires_in", 3600)
            return tokens.get("access_token"), tokens.get("refresh_token"), expires_in
        except requests.exceptions.RequestException as e:
            cls.log(f"Authentication failed: {e}")
            return None, None, None

    @classmethod
    def _get_access_token(cls):
        current_time = int(time.time())
        tokens = SolarPlatform.cache.get(ENPHASE_TOKENS)
        if tokens:
            stored_access_token, stored_refresh_token, expires_at = tokens
            if current_time < expires_at:
                return stored_access_token
        # Try to authenticate
        access_token, new_refresh_token, expires_in = cls.authenticate_enphase(
            ENPHASE_KEYS.user_email, ENPHASE_KEYS.user_password)
        if access_token:
            expires_at = current_time + expires_in
            SolarPlatform.cache.set(ENPHASE_TOKENS, (access_token, new_refresh_token,
                                    expires_at), expire=SolarPlatform.CACHE_EXPIRE_YEAR)
            return access_token
        else:
            cls.log("Authentication failed in _get_access_token")
            return None

    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_WEEK)
    def _fetch_raw_sites_data(cls) -> list:
        access_token = cls._get_access_token()
        if not access_token:
            return []

        all_systems = []
        page = 1
        size = 500  # Fetch 500 sites per page

        while True:
            url = f"{ENPHASE_BASE_URL}/api/v4/systems?key={ENPHASE_KEYS.api_key}&size={size}&page={page}"
            headers = {"Authorization": f"Bearer {access_token}"}
            try:
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
                break # Stop fetching if there's an error
        return all_systems

    @classmethod
    def get_sites_map(cls) -> Dict[str, SolarPlatform.SiteInfo]:
        raw_systems_data = cls._fetch_raw_sites_data()
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
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_HOUR * 2)
    def _get_raw_production(cls, site_id, reference_time) -> float:
        access_token = cls._get_access_token()
        if not access_token:
            return 0.0
        raw_system_id = cls.strip_vendorcodeprefix(site_id)
        url = f"{ENPHASE_BASE_URL}/api/v4/systems/{raw_system_id}/telemetry/production_micro?key={ENPHASE_KEYS.api_key}"
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            cls.log(f"Fetching production data from Enphase API for system {raw_system_id} at {reference_time}.")
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data
        except requests.exceptions.RequestException as e:
            cls.log(
                f"Failed to retrieve production data for system {raw_system_id}: {e}")
            return 0.0

    @classmethod
    def get_production(cls, site_id, reference_time) -> float:
        json = cls._get_raw_production(site_id, reference_time)
        values = json.get("values", [])
        for entry in reversed(values):
            if "value" in entry and entry["value"] is not None:
                latest_value = entry["value"]
                return latest_value 
        return 0.0

    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_MONTH())
    def _get_site_devices(cls, raw_system_id) -> dict:
        access_token = cls._get_access_token()
        if not access_token:
            return []
        url = f"{ENPHASE_BASE_URL}/api/v4/systems/{raw_system_id}/devices?key={ENPHASE_KEYS.api_key}"
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            cls.log(f"Fetching devices from Enphase API for system {raw_system_id} (metadata).")
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            json = response.json()
            return json
        except requests.exceptions.RequestException as e:
            cls.log(f"Failed to retrieve devices for system {raw_system_id}: {e}")
            return []

    @classmethod
    def get_batteries_metadata(cls, raw_system_id) -> list:
        json = cls._get_site_devices(raw_system_id)
        devices = json.get("devices", [])

        battery_devices = []
        for device in devices:
            if "encharge" in device:
                encharge_value = device["encharge"]  # Get the value associated with "encharge"
                if isinstance(encharge_value, list) and encharge_value:  # Check if it's a non-empty list
                    battery_devices.append(device)  # Add the device to the list

        return battery_devices

    # Separate call for fetching battery SOE (cached for a shorter period)
    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_HOUR * 4)
    def _get_battery_state_of_energy(cls, raw_system_id, serial_number):
        access_token = cls._get_access_token()
        if not access_token:
            return None
        url = f"{ENPHASE_BASE_URL}/api/v4/systems/{raw_system_id}/devices/encharges/{serial_number}/telemetry?key={ENPHASE_KEYS.api_key}"
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            cls.log(f"Fetching battery telemetry for system {raw_system_id}, battery {serial_number}.")
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            json = response.json()
            return json
        except requests.exceptions.RequestException as e:
            cls.log(f"Failed to retrieve telemetry for battery {serial_number} in system {raw_system_id}: {e}")
            return None

    # get_batteries_soe now first retrieves cached metadata, then queries telemetry individually.
    @classmethod
    def get_batteries_soe(cls, site_id) -> list:
        raw_system_id = cls.strip_vendorcodeprefix(site_id)
        batteries = cls.get_batteries_metadata(raw_system_id)
        battery_states = []
        for battery in batteries:
            serial_number = battery.get("serial_number")
            model = battery.get("model", "Unknown")
            json = cls._get_battery_state_of_energy(raw_system_id, serial_number)
            soe = json.get("state_of_charge")
            battery_states.append({
                "serialNumber": serial_number,
                "model": model,
                "stateOfEnergy": soe
            })
        return battery_states

    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_HOUR * 2)
    def get_alerts(cls) -> list:
        access_token = cls._get_access_token()
        if not access_token:
            return []
        url = f"{ENPHASE_BASE_URL}/api/v4/systems?key={ENPHASE_KEYS.api_key}"
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            cls.log("Fetching Enphase systems for alert processing.")
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            systems = response.json().get("systems", [])
            alerts = []
            for system in systems:
                status = system.get("status", "normal").lower()
                if status != "normal":
                    raw_system_id = system.get("system_id")
                    site_id = cls.add_vendorcodeprefix(raw_system_id)
                    alert_type = StandardErrorCodes.API_ERROR.value
                    details = f"System status is {status}."
                    severity = 50  # Adjust severity based on your criteria
                    first_triggered = datetime.utcnow()
                    alert = SolarPlatform.SolarAlert(
                        site_id, alert_type, severity, details, first_triggered)
                    alerts.append(alert)
            return alerts
        except requests.exceptions.RequestException as e:
            cls.log(f"Failed to retrieve alerts from Enphase API: {e}")
            return []


if __name__ == "__main__":
    access_token = EnphasePlatform._get_access_token()
    if not access_token:
        print("Unable to authenticate with Enphase API.")
        exit(1)
    sites = EnphasePlatform.get_sites_map()
    if sites:
        site_id = next(iter(sites.keys()))
        production = EnphasePlatform.get_production(
            site_id, SolarPlatform.get_recent_noon())
        print("Production Data:", production)
        battery_data = EnphasePlatform.get_batteries_soe(site_id)
        print("Battery Data:", battery_data)
        alerts = EnphasePlatform.get_alerts()
        print("Alerts:", alerts)
    else:
        print("No systems found in Enphase account.")
