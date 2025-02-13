import time
import requests
import base64
from datetime import datetime
from api_keys import ENPHASE_CLIENT_ID, ENPHASE_CLIENT_SECRET, ENPHASE_API_KEY, \
                     ENPHASE_USER_EMAIL, ENPHASE_USER_PASSWORD

import SolarPlatform

ENPHASE_BASE_URL = "https://api.enphaseenergy.com"
ENPHASE_TOKENS = "Enphase Tokens"
ENPHASE_SITE_URL = "https://enphaseenergy.com/systems/"

from enum import Enum

# Shared standard error codes across vendors.
class StandardErrorCodes(Enum):
    NO_COMMUNICATION = "NO_COMMUNICATION"
    CONFIG_ERROR = "CONFIG_ERROR"
    HARDWARE_ERROR = "HARDWARE_ERROR"
    API_ERROR = "API_ERROR"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"

class EnphasePlatform(SolarPlatform):

    @classmethod
    def get_vendorcode(cls):
        return "EN"

    @staticmethod
    def get_basic_auth_header(client_id, client_secret):
        credentials = f"{client_id}:{client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        return {"Authorization": f"Basic {encoded_credentials}"}

    @staticmethod
    def authenticate_enphase(username, password, refresh_token=None):
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
        headers = EnphasePlatform.get_basic_auth_header(ENPHASE_CLIENT_ID, ENPHASE_CLIENT_SECRET)
        try:
            response = requests.post(url, data=data, headers=headers)
            response.raise_for_status()
            tokens = response.json()
            expires_in = tokens.get("expires_in", 3600)
            return tokens.get("access_token"), tokens.get("refresh_token"), expires_in
        except requests.exceptions.RequestException as e:
            SolarPlatform.log(f"Authentication failed: {e}")
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
        access_token, new_refresh_token, expires_in = cls.authenticate_enphase(ENPHASE_USER_EMAIL, ENPHASE_USER_PASSWORD)
        if access_token:
            expires_at = current_time + expires_in
            SolarPlatform.cache.set(ENPHASE_TOKENS, (access_token, new_refresh_token, expires_at), expire=SolarPlatform.CACHE_EXPIRE_YEAR)
            return access_token
        else:
            SolarPlatform.log("Authentication failed in _get_access_token")
            return None

    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_WEEK)
    def get_sites_map(cls) -> dict:
        access_token = cls._get_access_token()
        if not access_token:
            return {}
        url = f"{ENPHASE_BASE_URL}/api/v4/systems?key={ENPHASE_API_KEY}"
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            systems = response.json().get("systems", [])
            sites_dict = {}
            for system in systems:
                raw_system_id = system.get("system_id")
                site_id = cls.add_vendorcodeprefix(raw_system_id)
                name = system.get("name", f"System {raw_system_id}")
                location = system.get("location", {})
                zipcode = location.get("zip", "48071")
                latitude = location.get("lat")
                longitude = location.get("lon")
                if latitude is None or longitude is None:
                    latitude, longitude = SolarPlatform.get_coordinates(zipcode)
                site_url = ENPHASE_SITE_URL + str(raw_system_id)
                site_info = SolarPlatform.SiteInfo(site_id, name, site_url, zipcode, latitude, longitude)
                sites_dict[site_id] = site_info
            return sites_dict
        except requests.exceptions.RequestException as e:
            SolarPlatform.log(f"Failed to retrieve Enphase systems: {e}")
            return {}

    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_HOUR * 2)
    def get_production(cls, site_id, reference_time) -> float:
        access_token = cls._get_access_token()
        if not access_token:
            return 0.0
        raw_system_id = cls.strip_vendorcodeprefix(site_id)
        url = f"{ENPHASE_BASE_URL}/api/v4/systems/{raw_system_id}/telemetry/production_micro?key={ENPHASE_API_KEY}"
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            SolarPlatform.log(f"Fetching production data from Enphase API for system {raw_system_id} at {reference_time}.")
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            values = data.get("values", [])
            latest_value = next((entry.get("value") for entry in reversed(values) if entry.get("value") is not None), 0.0)
            return latest_value
        except requests.exceptions.RequestException as e:
            SolarPlatform.log(f"Failed to retrieve production data for system {raw_system_id}: {e}")
            return 0.0

    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_MONTH())
    def get_batteries_metadata(cls, raw_system_id) -> list:
        access_token = cls._get_access_token()
        if not access_token:
            return []
        url = f"{ENPHASE_BASE_URL}/api/v4/systems/{raw_system_id}/devices?key={ENPHASE_API_KEY}"
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            SolarPlatform.log(f"Fetching devices from Enphase API for system {raw_system_id} (metadata).")
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            devices = response.json().get("devices", [])
            battery_devices = [device for device in devices if device.get("type", "").lower() == "encharge"]
            return battery_devices
        except requests.exceptions.RequestException as e:
            SolarPlatform.log(f"Failed to retrieve devices for system {raw_system_id}: {e}")
            return []

    # Separate call for fetching battery SOE (cached for a shorter period)
    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_HOUR * 4)
    def get_battery_state_of_energy(cls, raw_system_id, serial_number):
        access_token = cls._get_access_token()
        if not access_token:
            return None
        url = f"{ENPHASE_BASE_URL}/api/v4/systems/{raw_system_id}/devices/encharges/{serial_number}/telemetry?key={ENPHASE_API_KEY}"
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            SolarPlatform.log(f"Fetching battery telemetry for system {raw_system_id}, battery {serial_number}.")
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            telemetry_data = response.json()
            soe = telemetry_data.get("state_of_charge")
            return soe
        except requests.exceptions.RequestException as e:
            SolarPlatform.log(f"Failed to retrieve telemetry for battery {serial_number} in system {raw_system_id}: {e}")
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
            soe = cls.get_battery_state_of_energy(raw_system_id, serial_number)
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
        url = f"{ENPHASE_BASE_URL}/api/v4/systems?key={ENPHASE_API_KEY}"
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            SolarPlatform.log("Fetching Enphase systems for alert processing.")
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
                    alert = SolarPlatform.SolarAlert(site_id, alert_type, severity, details, first_triggered)
                    alerts.append(alert)
            return alerts
        except requests.exceptions.RequestException as e:
            SolarPlatform.log(f"Failed to retrieve alerts from Enphase API: {e}")
            return []

if __name__ == "__main__":
    access_token = EnphasePlatform._get_access_token()
    if not access_token:
        SolarPlatform.log("Unable to authenticate with Enphase API.")
        exit(1)
    sites = EnphasePlatform.get_sites_map()
    if sites:
        site_id = next(iter(sites.keys()))
        production = EnphasePlatform.get_production(site_id, SolarPlatform.get_recent_noon())
        print("Production Data:", production)
        battery_data = EnphasePlatform.get_batteries_soe(site_id)
        print("Battery Data:", battery_data)
        alerts = EnphasePlatform.get_alerts()
        print("Alerts:", alerts)
    else:
        SolarPlatform.log("No systems found in Enphase account.")
