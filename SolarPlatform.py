import random
from typing import List, Dict, Union
from dataclasses import dataclass
from abc import ABC, abstractmethod
from zoneinfo import ZoneInfo
import math
from datetime import datetime

import pprint
import keyring
import diskcache
import pgeocode
import numpy as np
import streamlit as st

import api_keys

# Disk cache decorator to save remote API calls.
cache = diskcache.Cache(".")

if 'collection_running' not in cache:
    cache['collection_running'] = False
if 'collection_completed' not in cache:
    cache['collection_completed'] = False
if 'collection_logs' not in cache:
    cache['collection_logs'] = []
if 'global_logs' not in cache:
    cache['global_logs'] = ""

DEFAULT_TIMEZONE = "US/Eastern"

SELECT_TIMEZONES = [
    'US/Eastern',
    'US/Central',
    'US/Mountain',
    'US/Pacific',
    'Europe/London',
    'Europe/Berlin',
    'Asia/Tokyo'
]

@dataclass(frozen=True)
class BatteryInfo:
    serial_number: str
    model_name: str
    state_of_energy: str # State of energy / charge in percentage


@dataclass(frozen=True)
class AlertType:
    NO_COMMUNICATION = "NO_COMMUNICATION"
    PRODUCTION_ERROR = "PRODUCTION_ERROR"
    PANEL_ERROR = "PANEL_ERROR" # Microinverter or optimizer error
    CONFIG_ERROR = "CONFIG_ERROR"


@dataclass(frozen=True)
class SolarAlert:
    site_id: str
    alert_type: str
    severity: int  # severity in percentage (0-100% production down)
    details: str
    first_triggered: datetime

    def __post_init__(self):
        if not 0 <= self.severity <= 100:
            raise ValueError("Severity must be between 0 and 100.")


@dataclass(frozen=True)
class SiteInfo:
    site_id: str
    name: str
    url: str
    zipcode: str
    latitude: float
    longitude: float

def extract_vendor_code(site_id):
    if ':' in site_id:
        return site_id.split(':', 1)[0]
    else:
        raise ValueError(f"Invalid site_id: {site_id}. Expected a vendor code prefix + :")

@dataclass(frozen=True)
class ProductionRecord:
    site_id: str
    production_kw: Union[float, List[float]]

    def __post_init__(self):
        # Ensure production_kw is always a list of floats
        if isinstance(self.production_kw, float):
            object.__setattr__(self, 'production_kw', [self.production_kw])
        elif not isinstance(self.production_kw, list):
            raise TypeError("production_kw must be a float or a list of floats")
        else:
            for item in self.production_kw:
                if not isinstance(item, float):
                    raise TypeError("production_kw list must contain only floats")

    def __setstate__(self, state):
        object.__setattr__(self, '__dict__', state)
        self.__post_init__()

    def __hash__(self):
        # Include production_kw in the hash (convert list to tuple)
        return hash((self.site_id, tuple(self.production_kw)))

    def __eq__(self, other):
        if not isinstance(other, ProductionRecord):
            return NotImplemented
        return (self.site_id, tuple(self.production_kw)) == (other.site_id, tuple(other.production_kw))


def calculate_production_kw(item):
    if isinstance(item, list):
        return sum(item)
    elif isinstance(item, (int, float)) and not np.isnan(item):
        return item
    else:
        return 0.0

def get_now():
    return datetime.now(ZoneInfo(cache.get('TimeZone', DEFAULT_TIMEZONE)))
    
class SolarPlatform(ABC):

    @classmethod
    @abstractmethod
    def get_vendorcode(cls):
        pass

    @classmethod
    @abstractmethod
    # Returns a dict of site_id (which contains a vendor code prefix) to SiteInfo objects
    def get_sites_map(cls) -> Dict[str, SiteInfo]:
        pass

    @classmethod
    @abstractmethod
    # returns a list of production for each inverter on site
    def get_production(cls, site_id, reference_time) -> List[float]:
        pass

    @classmethod
    @abstractmethod
    # returns a list of BatteryInfos for a site
    def get_batteries_soe(cls, site_id) -> List[BatteryInfo]:
        pass

    @classmethod
    @abstractmethod
    # Returns a list of SolarAlerts
    def get_alerts(cls) -> List[SolarAlert]:
        pass

    @classmethod
    def add_vendorcodeprefix(cls, site_id):
        return cls.get_vendorcode() + ":" + str(site_id)

    @classmethod
    def strip_vendorcodeprefix(cls, site_id):
        if ':' in site_id:
            site_id_raw = site_id.split(':', 1)[1]
            return site_id_raw
        else:
            return site_id
        
    @classmethod
    def log(cls, message: str):
        formatted_str = pprint.pformat(message, depth=None, width=120)
        # Append to collection_logs if collection is running
        if cache['collection_running']:
            cache['collection_logs'] = cache['collection_logs'] + [formatted_str]
        st.write(formatted_str)
        cache['global_logs'] = cache['global_logs'] + formatted_str + "\n"

# Button to start the collection
CACHE_EXPIRE_HOUR = 3600
CACHE_EXPIRE_DAY = CACHE_EXPIRE_HOUR * 24
CACHE_EXPIRE_WEEK = CACHE_EXPIRE_DAY * 7
CACHE_EXPIRE_YEAR = CACHE_EXPIRE_DAY * 365

# Scatter monthly requests over a period of 10 days to avoid cache stampede.
def cache_expire_month():
    base = CACHE_EXPIRE_WEEK * 4
    offset = random.randint(-CACHE_EXPIRE_DAY * 5, CACHE_EXPIRE_DAY * 5)
    return base + offset


def disk_cache(expiration_seconds):
    def decorator(func):
        def wrapper(*args, **kwargs):
            cache_key = f"{func.__name__}_{args}_{kwargs}"
            if cache_key in cache:
                try:
                    return cache[cache_key]
                except KeyError:
                    pass
            result = func(*args, **kwargs)
            cache.set(cache_key, result, expire=expiration_seconds)
            return result
        return wrapper
    return decorator


nomi = pgeocode.Nominatim('us')

def haversine_distance(lat1, lon1, lat2, lon2):

    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * \
        math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    return c * 3958.8  # Earth radius in miles

@st.cache_data
def get_coordinates(zip_code):
    try:
        result = nomi.query_postal_code(zip_code)
        if result is None or math.isnan(result.latitude) or math.isnan(result.longitude):
            print(f"Failed to get coordinates for zip code: {zip_code}")
            result = nomi.query_postal_code(48071)
        return result.latitude, result.longitude
    except Exception as e:
        print(
            f"Exception thrown trying to get coordinates for zip code: {zip_code}")
        return 42.5, -83.1

def set_keyring_from_api_keys():
    """Sets API keys in the keyring based on variables in api_keys.py."""
    try:

        keyring.set_password("enphase", "client_id", api_keys.ENPHASE_CLIENT_ID)
        keyring.set_password("enphase", "client_secret", api_keys.ENPHASE_CLIENT_SECRET)
        keyring.set_password("enphase", "api_key", api_keys.ENPHASE_API_KEY)
        keyring.set_password("enphase", "user_email", api_keys.ENPHASE_USER_EMAIL)
        keyring.set_password("enphase", "user_password", api_keys.ENPHASE_USER_PASSWORD)

        # SolarEdge Keys (Storing individually)
        keyring.set_password("solaredge", "account_key", api_keys.SOLAREDGE_V2_ACCOUNT_KEY)
        keyring.set_password("solaredge", "api_key", api_keys.SOLAREDGE_V2_API_KEY)

        keyring.set_password("solark", "email", api_keys.SOLARK_EMAIL)
        keyring.set_password("solark", "password", api_keys.SOLARK_PASSWORD) 

        print("API keys set in keyring.")

    except AttributeError as e:
        print(f"Error: Missing API key in api_keys.py: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


# If you want to display fake data for screenshots
FAKE_DATA = False

def generate_fake_address():
    # Generate a random 4-digit number
    number = random.randint(1000, 9999)
    
    # List of common street names
    street_names = ["Main", "Oak", "Maple", "Pine", "Cedar", "Elm", "Willow", "Birch", "Ash", "Cherry"]
    # Choose a random street name
    street = random.choice(street_names)
    
    # List of common street types
    street_types = ["St", "Ave", "Rd", "Blvd", "Ln", "Dr", "Ct"]
    # Choose a random street type
    street_type = random.choice(street_types)
    
    # Combine the elements to create a fake address
    return f"{number} {street} {street_type}"


def generate_fake_site_id():
    # List of allowed prefixes
    prefixes = ["SE", "EN", "SA", "SMA", "SO"]
    # Choose a random prefix
    prefix = random.choice(prefixes)
    
    # Generate a random 7-digit number
    number = random.randint(1000000, 9999999)
    
    # Combine the prefix and number
    return f"{prefix}:{number}"