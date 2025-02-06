from abc import ABC, abstractmethod
import streamlit as st

#Shared classes and methods

class SolarPlatform(ABC):
#    log_container = st.empty()  # A Streamlit container to display log messages
    log_text = ""  # A string to store cumulative log messages

    @classmethod
    @abstractmethod
    def get_vendorcode():
        pass

    @classmethod
    @abstractmethod
    def get_sites():
        pass

    @classmethod
    @abstractmethod
    #returns a list of dictionaries with the following keys: serialNumber, model, stateOfEnergy
    def get_batteries_soe(site_id):
        pass

    @classmethod
    @abstractmethod
    def get_alerts(site_id):
        pass
    
    @classmethod
    def log(cls, message: str, container=None):
        # Use the provided container or the default shared container.
 #       if container is not None:
 #           cls.log_container = container

 #       container = container if container is not None else cls.log_container
        # Print to the command line.
        print(message)
        # Append the message to the class-level log text.
        cls.log_text += message + "\n"
        # Update the shared Streamlit container.
        if container is not None:
            container.text(cls.log_text)


import diskcache

cache = diskcache.Cache("/tmp/")  # Persistent cache

CACHE_EXPIRATION_WEEK = 7 * 24 * 60 * 60  # 1 week
CACHE_EXPIRATION_HOUR = 3600

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

