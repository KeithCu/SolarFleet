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
    def get_batteries_soc(site_id):
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

