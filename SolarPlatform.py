from abc import ABC, abstractmethod
import streamlit as st
from typing import List, Dict
import diskcache
import pprint
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional
import random

@dataclass
class SiteInfo:
    site_id: str
    name: str
    url: str
    zipcode: str
    inverters: List[str]

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
    site_name: str
    site_url: str
    alert_type: AlertType
    severity: int  # severity in percentage (0-100% production down)
    details: str
    first_triggered: str

    def __post_init__(self):
        if not (0 <= self.severity <= 100):
            raise ValueError("Severity must be between 0 and 100.")

@dataclass
class SolarProduction:
    site_id: str
    site_name: str
    site_zipcode: int
    site_production: float
    site_url: str

class SolarPlatform(ABC):
#    log_container = st.empty()  # A Streamlit container to display log messages
    log_text = ""  # A string to store cumulative log messages

    @classmethod
    @abstractmethod
    def get_vendorcode(cls):
        pass

    @classmethod
    @abstractmethod
    #Returns a map of siteid (string) SiteInfo objects
    def get_sites_map(cls) -> Dict[str, SiteInfo]:
        pass

    @classmethod
    @abstractmethod
    #returns production in KW at a particular time
    def get_production(cls, site_id, time) -> float:
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
