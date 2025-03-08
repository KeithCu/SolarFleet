import requests
import time
import json
import os
import threading

import SolarPlatform

lock = threading.Lock()

def geocode_address(address):
    with lock:
        return _geocode_address(address)

@SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_NEVER)
def _geocode_address(address):
    """Geocode an address using Nominatim API and return (latitude, longitude)."""

    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": address,
        "format": "json",
        "limit": 1
    }
    headers = {
        "User-Agent": "Solar Monitoring Dashboard/1.0 (service@absolutesolar.com)"
    }

    try:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()  # Raise an exception for bad status codes
        data = response.json()

        # Check if we got a result
        if data:
            lat = float(data[0]["lat"])
            lon = float(data[0]["lon"])
            result = (lat, lon)
            print (f"Geocoded {address} to {result}")
            return result
        else:
            print(f"No results found for {address}")
            return (None, None)

    except Exception as e:
        print(f"Error geocoding {address}: {e}")
        return (None, None)

    finally:
        # Be nice to the Nominatim server
        time.sleep(2)
