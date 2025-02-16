import aiohttp
import async_timeout
import asyncio
import time
import json
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List

import requests

import SolarPlatform

# API endpoints for Solis
RESOURCE_PREFIX = '/v1/api/'
USER_STATION_LIST = RESOURCE_PREFIX + 'userStationList'
STATION_DETAIL = RESOURCE_PREFIX + 'stationDetail'
COLLECTOR_LIST = RESOURCE_PREFIX + 'collectorList'
STATION_DAY = RESOURCE_PREFIX + 'stationDay'
ALARM_LIST = RESOURCE_PREFIX + 'alarmList'

# A base URL for constructing a site URL (for display purposes)
SOLIS_SITE_URL = "https://soliscloud.example.com/station/"

# Custom exception for Solis API errors
class SolisCloudAPIError(Exception):
    pass

class SolisCloudPlatform(SolarPlatform.SolarPlatform):
    _session: aiohttp.ClientSession = None

    @classmethod
    async def get_session(cls) -> aiohttp.ClientSession:
        if cls._session is None or cls._session.closed:
            cls._session = aiohttp.ClientSession()
        return cls._session

    @classmethod
    async def close_session(cls):
        if cls._session and not cls._session.closed:
            await cls._session.close()

    @classmethod
    def get_vendorcode(cls):
        return "SO"

    @classmethod
    async def _async_fetch_api_data(cls, endpoint: str, params: dict, ttl: int = SolarPlatform.CACHE_EXPIRE_HOUR) -> dict:
        # Replace with your actual API domain and any authentication logic as needed.
        domain = "https://api.soliscloud.example.com"
        url = domain.rstrip("/") + endpoint
        headers = {
            "Content-Type": "application/json"
        }
        session = await cls.get_session()
        try:
            async with async_timeout.timeout(10):
                async with session.post(url, json=params, headers=headers) as response:
                    if response.status != 200:
                        raise SolisCloudAPIError(f"HTTP error: {response.status}")
                    data = await response.json()
                    return data
        except asyncio.TimeoutError:
            raise SolisCloudAPIError("Timeout error occurred during API call")

    @classmethod
    def _fetch_api_data(cls, endpoint: str, params: dict, ttl: int = SolarPlatform.CACHE_EXPIRE_HOUR) -> dict:
        return asyncio.run(cls._async_fetch_api_data(endpoint, params, ttl))

    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_HOUR)
    def get_user_station_list(cls, page_no: int = 1, page_size: int = 20) -> dict:
        params = {"pageNo": page_no, "pageSize": page_size}
        return cls._fetch_api_data(USER_STATION_LIST, params)

    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_HOUR)
    def get_station_detail(cls, station_id: int) -> dict:
        params = {"id": station_id}
        return cls._fetch_api_data(STATION_DETAIL, params)

    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_HOUR)
    def get_collector_list(cls, page_no: int = 1, page_size: int = 20, station_id: int = None) -> dict:
        params = {"pageNo": page_no, "pageSize": page_size}
        if station_id:
            params["stationId"] = station_id
        return cls._fetch_api_data(COLLECTOR_LIST, params)

    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_HOUR)
    def get_station_day(cls, station_id: int, time_str: str = None, currency: str = "USD", time_zone: int = 0) -> dict:
        if time_str is None:
            time_str = datetime.utcnow().strftime("%Y-%m-%d")
        params = {"money": currency, "time": time_str, "timeZone": time_zone, "id": station_id}
        return cls._fetch_api_data(STATION_DAY, params)

    @classmethod
    def process_station_data(cls, raw_data: dict) -> dict:
        # Transform the raw station list data into a dict with a "stations" key.
        processed = {"stations": raw_data.get("data", [])}
        return processed

    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_HOUR)
    def get_sites_map(cls) -> Dict[str, SolarPlatform.SiteInfo]:
        # Fetch station list from the Solis API and map each station to a SiteInfo object.
        raw_data = cls.get_user_station_list(page_no=1, page_size=100)
        processed = cls.process_station_data(raw_data)
        stations_list = processed.get("stations", [])
        sites_dict = {}
        for station in stations_list:
            raw_station_id = station.get("id")
            if raw_station_id is None:
                continue
            site_id = cls.add_vendorcodeprefix(raw_station_id)
            name = station.get("name", "Unknown Station")
            url = SOLIS_SITE_URL + str(raw_station_id)
            zipcode = station.get("zipcode") or station.get("location", {}).get("zip", "48071")
            # Use SolarPlatform.get_coordinates to resolve latitude/longitude.
            latitude, longitude = SolarPlatform.get_coordinates(zipcode)
            site_info = SolarPlatform.SiteInfo(site_id, name, url, zipcode, latitude, longitude)
            sites_dict[site_id] = site_info
        return sites_dict

    @classmethod
    def get_production(cls, site_id, reference_time) -> List[float]:
        # Use the station day endpoint to fetch production data.
        raw_station_id = cls.strip_vendorcodeprefix(site_id)
        try:
            station_id_int = int(raw_station_id)
        except ValueError:
            station_id_int = raw_station_id
        date_str = reference_time.strftime("%Y-%m-%d")
        production_data = cls.get_station_day(station_id=station_id_int, time_str=date_str)
        # Assume the returned data includes an "inverters" list with power values.
        inverters = production_data.get("inverters", [])
        productions = []
        for inverter in inverters:
            power = inverter.get("power", 0.0)
            productions.append(round(power, 2))
        # Fallback if no inverter list exists.
        if not productions and "production" in production_data:
            productions = [round(production_data.get("production", 0.0), 2)]
        return productions

    @classmethod
    def get_batteries_soe(cls, site_id) -> List:
        # Fetch station detail and extract battery information.
        raw_station_id = cls.strip_vendorcodeprefix(site_id)
        try:
            station_id_int = int(raw_station_id)
        except ValueError:
            station_id_int = raw_station_id
        detail = cls.get_station_detail(station_id=station_id_int)
        batteries = detail.get("batteries", [])
        battery_states = []
        for battery in batteries:
            battery_states.append({
                "serialNumber": battery.get("serialNumber"),
                "model": battery.get("model", "Unknown"),
                "stateOfEnergy": battery.get("stateOfEnergy", 0.0)
            })
        return battery_states

    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_HOUR)
    def get_alerts(cls) -> List[SolarPlatform.SolarAlert]:
        alerts = []
        try:
            data = cls._fetch_api_data(ALARM_LIST, params={})
            alarms = data.get("alarms", [])
            for alarm in alarms:
                raw_station_id = alarm.get("siteId")
                if not raw_station_id:
                    continue
                site_id = cls.add_vendorcodeprefix(raw_station_id)
                alarm_type = alarm.get("type", "")
                # Map Solis-specific alarm types to the standard SolarPlatform.AlertType.
                if alarm_type == "COMM_FAULT":
                    alert_type = SolarPlatform.AlertType.NO_COMMUNICATION
                elif alarm_type == "PROD_ERROR":
                    alert_type = SolarPlatform.AlertType.PRODUCTION_ERROR
                elif alarm_type == "PANEL_ERROR":
                    alert_type = SolarPlatform.AlertType.PANEL_ERROR
                else:
                    alert_type = SolarPlatform.AlertType.CONFIG_ERROR
                severity = alarm.get("impact", 0)
                details = alarm.get("details", "")
                first_triggered_str = alarm.get("firstTrigger", "")
                if first_triggered_str and first_triggered_str.endswith("Z"):
                    first_triggered = datetime.fromisoformat(first_triggered_str.replace("Z", "+00:00"))
                else:
                    first_triggered = datetime.utcnow()
                alert_obj = SolarPlatform.SolarAlert(site_id, alert_type, severity, details, first_triggered)
                alerts.append(alert_obj)
        except Exception as e:
            cls.log(f"Error fetching alerts from Solis API: {e}")
        return alerts

# Example usage (for testing purposes)
if __name__ == "__main__":
    try:
        # Get and display station list
        raw_stations = SolisCloudPlatform.get_user_station_list(page_no=1, page_size=100)
        stations = SolisCloudPlatform.process_station_data(raw_stations)
        print("User Station List:")
        print(json.dumps(stations, indent=2))

        # Test fetching station detail, production, and alerts as needed.
    except Exception as e:
        print("Error during API call:", e)
    finally:
        asyncio.run(SolisCloudPlatform.close_session())
