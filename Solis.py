import aiohttp
import async_timeout
import asyncio
import time
import json
import hmac
import hashlib
from datetime import datetime
from typing import Dict, List

# Import your SolarPlatform base class and utilities
import SolarPlatform
from SolarPlatform import disk_cache, CACHE_EXPIRE_HOUR, CACHE_EXPIRE_WEEK, SiteInfo, SolarAlert, ProductionRecord

# API endpoints
RESOURCE_PREFIX = '/v1/api/'
USER_STATION_LIST = RESOURCE_PREFIX + 'userStationList'
STATION_DETAIL = RESOURCE_PREFIX + 'stationDetail'
COLLECTOR_LIST = RESOURCE_PREFIX + 'collectorList'
STATION_DAY = RESOURCE_PREFIX + 'stationDay'
# ... add additional endpoints as needed

# Custom exception
class SolisCloudAPIError(Exception):
    pass

class SolisCloudPlatform(SolarPlatform.SolarPlatform):
    _session: aiohttp.ClientSession = None  # Shared session

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
        return "SC"  # Vendor code for SolisCloud

    @classmethod
    async def _async_fetch_api_data(cls, endpoint: str, params: dict, ttl: int = CACHE_EXPIRE_HOUR) -> dict:
        """
        Asynchronously fetch raw data from the SolisCloud API using a shared session.
        Raw responses are returned for further processing.
        """
        # FIXME: Replace with your actual API domain and authentication/signing logic.
        domain = "https://api.soliscloud.example.com"
        url = domain.rstrip("/") + endpoint
        headers = {
            "Content-Type": "application/json"
        }
        # TODO: Add authentication headers using your key/secret if needed.
        # Example (if HMAC is required):
        # signature = hmac.new(b'your_secret', url.encode(), hashlib.sha256).hexdigest()
        # headers["Authorization"] = f"Bearer {signature}"

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
    def _fetch_api_data(cls, endpoint: str, params: dict, ttl: int = CACHE_EXPIRE_HOUR) -> dict:
        """
        Synchronous wrapper around the async API call.
        This function is decorated with SolarPlatform.disk_cache so that raw API responses are cached.
        """
        return asyncio.run(cls._async_fetch_api_data(endpoint, params, ttl))

    @classmethod
    @disk_cache(CACHE_EXPIRE_HOUR)
    def get_user_station_list(cls, page_no: int = 1, page_size: int = 20, nmi_code: str = None) -> dict:
        params = {"pageNo": page_no, "pageSize": page_size}
        if nmi_code:
            params["nmiCode"] = nmi_code
        return cls._fetch_api_data(USER_STATION_LIST, params)

    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_HOUR)
    def get_station_detail(cls, station_id: int, nmi_code: str = None) -> dict:
        params = {"id": station_id}
        if nmi_code:
            params["nmiCode"] = nmi_code
        return cls._fetch_api_data(STATION_DETAIL, params)

    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_HOUR)
    def get_collector_list(cls, page_no: int = 1, page_size: int = 20, station_id: int = None, nmi_code: str = None) -> dict:
        params = {"pageNo": page_no, "pageSize": page_size}
        if station_id:
            params["stationId"] = station_id
        if nmi_code:
            params["nmiCode"] = nmi_code
        return cls._fetch_api_data(COLLECTOR_LIST, params)

    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_HOUR)
    def get_station_day(cls, station_id: int = None, nmi_code: str = None, currency: str = "USD", time_str: str = None, time_zone: int = 0) -> dict:
        """
        Retrieve daily station data.
        NOTE: Hardcoded currency and timezone values are marked as FIXME.
        """
        if time_str is None:
            time_str = datetime.utcnow().strftime("%Y-%m-%d")
        params = {"money": currency, "time": time_str, "timeZone": time_zone}
        if station_id is not None and nmi_code is None:
            params["id"] = station_id
        elif station_id is None and nmi_code is not None:
            params["nmiCode"] = nmi_code
        else:
            raise SolisCloudAPIError("Only pass one of station_id or nmi_code as identifier")
        return cls._fetch_api_data(STATION_DAY, params)

    # Business logic wrappers (uncached) can use the above raw API methods.
    @classmethod
    def process_station_data(cls, raw_data: dict) -> dict:
        # TODO: Implement any transformation logic as needed.
        processed = {"stations": raw_data.get("data", [])}
        return processed

# Example usage (for testing purposes)
if __name__ == "__main__":
    try:
        # Get station list
        raw_stations = SolisCloudPlatform.get_user_station_list(page_no=1, page_size=100)
        stations = SolisCloudPlatform.process_station_data(raw_stations)
        print("User Station List:")
        print(json.dumps(stations, indent=2))

        # Get station detail (uncomment and set a valid station_id)
        # raw_detail = SolisCloudPlatform.get_station_detail(station_id=12345)
        # detail = SolisCloudPlatform.process_station_data(raw_detail)
        # print("Station Detail:")
        # print(json.dumps(detail, indent=2))

        # Get station day data (uncomment and adjust parameters)
        # raw_day = SolisCloudPlatform.get_station_day(station_id=12345, time_str="2025-02-14")
        # day_data = SolisCloudPlatform.process_station_data(raw_day)
        # print("Station Day Data:")
        # print(json.dumps(day_data, indent=2))
    except Exception as e:
        print("Error during API call:", e)
    finally:
        # Ensure the shared session is closed when done
        asyncio.run(SolisCloudPlatform.close_session())
