from abc import ABC, abstractmethod
import streamlit as st
from typing import List, Dict
import diskcache
import pprint
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional
import random
import math
from datetime import datetime, timedelta, time

@dataclass
class SiteInfo:
    site_id: str
    name: str
    url: str
    zipcode: str

@dataclass
class BatteryInfo:
    serial_number: str
    model_name: str
    state_of_energy: str

class AlertType:
    NO_COMMUNICATION = "NO_COMMUNICATION"
    CONFIG_ERROR = "CONFIG_ERROR"
    HARDWARE_ERROR = "HARDWARE_ERROR"
    MLPE_ERROR = "MLPE_ERROR"

@dataclass
class SolarAlert:
    site_id: str
    name: str
    alert_type: str
    severity: int  # severity in percentage (0-100% production down)
    details: str
    first_triggered: str

    def __post_init__(self):
        if not (0 <= self.severity <= 100):
            raise ValueError("Severity must be between 0 and 100.")

#In memory production information
@dataclass
class SolarProduction:
    site_id: str
    site_name: str
    site_zipcode: int
    site_production: float
    site_url: str

#In Sqlite, for each day, we store a set of ProductionRecord objects, one for each site.
@dataclass
class ProductionRecord:
    vendor_code: str
    site_id: str
    production: float
    #Two ProductionRecord objects are considered equal if they share the same vendor and site.

    def __hash__(self):
        return hash((self.vendor_code, self.site_id))

    def __eq__(self, other):
        if not isinstance(other, ProductionRecord):
            return NotImplemented
        return (self.vendor_code, self.site_id) == (other.vendor_code, other.site_id)

class SolarPlatform(ABC):
#    log_container = st.empty()  # A Streamlit container to display log messages
    log_text = ""  # A string to store cumulative log messages

    @classmethod
    @abstractmethod
    def get_vendorcode(cls):
        pass

    @classmethod
    @abstractmethod
    #Returns a map of siteid to SiteInfo objects
    def get_sites_map(cls) -> Dict[str, SiteInfo]:
        pass

    @classmethod
    @abstractmethod
    #returns production in KW at a particular time
    def get_production(cls, site_id, reference_time) -> float:
        pass

    @classmethod
    @abstractmethod
    #returns a list of BatteryInfos for a site
    def get_batteries_soe(cls, site_id) -> List[BatteryInfo]:
        pass

    @classmethod
    @abstractmethod
    #Returns a list of SolarAlerts
    def get_alerts(cls) -> List[SolarAlert]:
        pass
    
    @classmethod
    def log(cls, message: str, container=None):
        # Use the provided container or the default shared container.
 #       if container is not None:
 #           cls.log_container = container

 #       container = container if container is not None else cls.log_container
        # Print to the command line.
        formatted_str = pprint.pformat(message, depth=None, width=120)
        print(formatted_str)
        # Append the message to the class-level log text.
        cls.log_text += message + "\n"
        # Update the shared Streamlit container.
        if container is not None:
            container.text(cls.log_text)

#Disk cache decorator to save API calls.
cache = diskcache.Cache("/tmp/")  # Persistent cache

CACHE_EXPIRE_HOUR = 3600
CACHE_EXPIRE_DAY = CACHE_EXPIRE_HOUR * 24
CACHE_EXPIRE_WEEK = CACHE_EXPIRE_DAY * 7
CACHE_EXPIRE_YEAR = CACHE_EXPIRE_DAY * 365

#Scatter monthly requests over a period of 10 days to avoid cache stampede.
def CACHE_EXPIRE_MONTH():
    base = CACHE_EXPIRE_WEEK * 4
    offset = random.randint(-CACHE_EXPIRE_DAY * 5, CACHE_EXPIRE_DAY * 5)
    return base + offset

def disk_cache(expiration_seconds):
    def decorator(func):
        def wrapper(*args, **kwargs):
            cache_key = f"{func.__name__}_{args}_{kwargs}"
            
            if cache_key in cache:
                return cache[cache_key]  # Return cached value

            result = func(*args, **kwargs)
            cache.set(cache_key, result, expire=expiration_seconds)  # Store result with expiration
            return result
        
        return wrapper
    return decorator

def get_recent_noon() -> str:
    # Get current local time (with tz info)
    now = datetime.now().astimezone()
    today = now.date()
    
    # Construct the threshold: today at 12:30 local time
    threshold = datetime.combine(today, time(12, 30), tzinfo=now.tzinfo)
    
    # Decide which noon to use:
    #   If now is after or equal to 12:30, use today at noon (12:00);
    #   otherwise, use yesterday at noon.
    if now >= threshold:
        measurement_date = today
    else:
        measurement_date = today - timedelta(days=1)
    
    measurement_dt = datetime.combine(measurement_date, time(12, 0), tzinfo=now.tzinfo)
    
    # Format the datetime into the desired string.
    # The example format is: "2022-11-14T11:30:54.276805300Z"
    # Python’s microsecond precision gives 6 digits. To mimic 9 digits, we append "000".
    dt_str = measurement_dt.strftime("%Y-%m-%dT%H:%M:%S.%f") + "000"
    
    # Format the timezone offset:
    # If the offset is 0, we use "Z"; otherwise, we insert a colon to get ±HH:MM.
    offset = measurement_dt.utcoffset()
    if offset == timedelta(0):
        tz_str = "Z"
    else:
        tz_offset = measurement_dt.strftime("%z")  # e.g., "+0100"
        tz_str = tz_offset[:3] + ":" + tz_offset[3:]  # becomes "+01:00"
    
    return dt_str + tz_str

import pgeocode
nomi = pgeocode.Nominatim('us')

def haversine_distance(lat1, lon1, lat2, lon2):

    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    return c * 3958.8  # Earth radius in miles

def get_coordinates(zip_code):
    try:
        result = nomi.query_postal_code(zip_code)
        if result is None or math.isnan(result.latitude) or math.isnan(result.longitude):
            print(f"Failed to get coordinates for zip code: {zip_code}")
            return None, None
        return result.latitude, result.longitude
    except Exception as e:
        print(f"Error getting coordinates for zip code {zip_code}: {e}")
        return None, None
