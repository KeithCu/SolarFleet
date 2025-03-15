import requests
import time
import json
import os
import threading

lock = threading.Lock()

def load_cache():
    """Load the cache from a JSON file, or return an empty dict if it doesn't exist or fails."""
    cache_file = "geocode_cache.json"
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading cache: {e}")
            return {}
    else:
        return {}

def save_cache(cache):
    """Save the cache to a JSON file with indentation for readability."""
    cache_file = "geocode_cache.json"
    try:
        with open(cache_file, "w") as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        print(f"Error saving cache: {e}")

# Initialize the cache at module level
cache = load_cache()

def geocode_address(address):
    """Geocode an address, using the cache if available, and update the cache on new successful results."""
    global cache
    with lock:
        if address in cache:
            #print(f"Cache hit for {address}")
            return tuple(cache[address])  # Convert list from JSON to tuple
        else:
            print(f"Geocoding {address} via API")
            result = _geocode_address(address)
            cache[address] = list(result)
            save_cache(cache)
            return result

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
            print(f"Geocoded {address} to {result}")
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

if __name__ == "__main__":
    coords = geocode_address("1600 Amphitheatre Parkway, Mountain View, CA")
    print(f"Coordinates: {coords}")
    
    coords = geocode_address("1600 Amphitheatre Parkway, Mountain View, CA")
    print(f"Coordinates from cache: {coords}")