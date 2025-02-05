from abc import ABC, abstractmethod
import streamlit as st

class SolarPlatform(ABC):
    log_container = st.empty()  # A Streamlit container to display log messages
    log_text = ""  # A string to store cumulative log messages

    @abstractmethod
    def get_sites(self):
        pass

    @abstractmethod
    def get_batteries_soc(self, site_id):
        pass

    @abstractmethod
    def get_alerts(self, site_id):
        pass
    
    @classmethod
    def log(cls, message: str, container=None):
        # Use the provided container or the default shared container.
        if container is not None:
            cls.log_container = container

        container = container if container is not None else cls.log_container
        # Print to the command line.
        print(message)
        # Append the message to the class-level log text.
        cls.log_text += message + "\n"
        # Update the shared Streamlit container.
        container.text(cls.log_text)

# Define vendor short codes
VENDOR_CODES = {
    "SolarEdge": "SE",
    "Enphase": "EN",
    "SolArk": "SA",
    "Sonnen": "SN",
    "SMA": "SMA",
}

# Function to retrieve vendor code
def get_vendor_code(vendor_name):
    return VENDOR_CODES[vendor_name]

from datetime import datetime
from sqlalchemy import PrimaryKeyConstraint, create_engine, Column, String, Float, DateTime, Integer, Float, Boolean
from sqlalchemy.orm import declarative_base

Base = declarative_base()

# Define tables
class Alert(Base):
    # Define the composite primary key using vendor_id and system_id
    vendor_id = Column(String(2), nullable=False)
    system_id = Column(String(30), nullable=False)
    
    # Other columns
    alert_type = Column(String, nullable=False)
    message    = Column(String, nullable=False)

    # New column for the site URL (optional URL field)
    site_url   = Column(String, nullable=False)
    timestamp  = Column(DateTime, default=datetime.utcnow)
    resolved   = Column(DateTime, nullable=True)
    history    = Column(String, default="")  # Track changes/updates

    __table_args__ = (
        PrimaryKeyConstraint('vendor_id', 'system_id'),
    )


# Battery schema to store last 3 data points
class Battery(Base):
    __tablename__ = "batteries"
    serial_number = Column(String, primary_key=True)
    model_number = Column(String, nullable=False)
    site_id = Column(String, nullable=False)
    site_name = Column(String, nullable=False)
    state_of_energy_1 = Column(Float, nullable=True)
    state_of_energy_2 = Column(Float, nullable=True)
    state_of_energy_3 = Column(Float, nullable=True)
    last_updated = Column(DateTime, default=datetime.utcnow)