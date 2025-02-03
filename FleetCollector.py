from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import sys
import time
import requests
from sqlalchemy import create_engine, Column, String, Float, DateTime, Integer, Float, Boolean

from sqlalchemy.orm import sessionmaker, declarative_base
from webdriver_manager.chrome import ChromeDriverManager

# Database setup using SQLAlchemy
DATABASE_URL = "sqlite:///solar_alerts.db"
Base = declarative_base()
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)

sys.path.insert(0, '.')
from Enphase import *
from SolarEdge import *
from SolArk import *

# Define tables
class Alert(Base):
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    inverter = Column(String, nullable=False)
    alert_type = Column(String, nullable=False)
    message = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    resolved = Column(Boolean, default=False)
    history = Column(String, default="")  # Track changes/updates

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

# Initialize database
def init_db():
    Base.metadata.create_all(engine)

def is_data_recent():
    """Check if any site has been updated within the last day."""
    session = SessionLocal()
    recent_battery = session.query(Battery).order_by(Battery.last_updated.desc()).first()
    session.close()
    return recent_battery and (datetime.utcnow() - recent_battery.last_updated) < timedelta(days=1)


def add_alert_if_not_exists(inverter, alert_type, message):
    """Add an alert to the database if it doesn't already exist as an open alert."""
    session = SessionLocal()
    existing_alert = session.query(Alert).filter(
        Alert.inverter == inverter,
        Alert.alert_type == alert_type,
        Alert.message == message,
        Alert.resolved == False
    ).first()
    
    if not existing_alert:
        new_alert = Alert(
            inverter=inverter,
            alert_type=alert_type,
            message=message,
            timestamp=datetime.utcnow(),
            resolved=False,
            history=""
        )
        session.add(new_alert)
        session.commit()
    session.close()


# Battery Data Update Function
def update_battery_data(site_id, site_name, batteries):
    """Update the battery data, maintaining only the last 3 records."""
    session = SessionLocal()
    for battery in batteries:
        serial_number = battery['serialNumber']
        model_number = battery['modelNumber']
        soe = battery.get('stateOfEnergy')
        
        existing_battery = session.query(Battery).filter(Battery.serial_number == serial_number).first()
        if existing_battery:
            existing_battery.state_of_energy_3 = existing_battery.state_of_energy_2
            existing_battery.state_of_energy_2 = existing_battery.state_of_energy_1
            existing_battery.state_of_energy_1 = soe
            existing_battery.last_updated = datetime.utcnow()
        else:
            new_battery = Battery(
                serial_number=serial_number,
                model_number=model_number,
                site_id=site_id,
                site_name=site_name,
                state_of_energy_1=soe,
                state_of_energy_2=None,
                state_of_energy_3=None,
                last_updated=datetime.utcnow()
            )
            session.add(new_battery)
    session.commit()
    session.close()


def main():
    init_db()
    if is_data_recent():
        print("Skipping updates as data is recent enough.")
        return

    SOLAREDGE_API_KEY = 'kkkk'
    solaredge_sites = get_solaredge_sites(SOLAREDGE_API_KEY)
    for site in solaredge_sites:
        site_id = site.get('id')
        site_name = site.get('name')
        batteries = get_solaredge_battery_state_of_energy(SOLAREDGE_API_KEY, site_id)
        update_battery_data(site_id, site_name, batteries)

    global ENPHASE_ACCESS_TOKEN
    ENPHASE_ACCESS_TOKEN = authenticate_enphase()
    if not ENPHASE_ACCESS_TOKEN:
        print("Unable to authenticate with Enphase API.")
        return

    enphase_systems = get_enphase_systems()
    for system in enphase_systems:
        system_id = system.get('system_id')
        system_name = system.get('name')
        batteries = get_enphase_battery_state_of_energy(system_id)
        update_battery_data(system_id, system_name, batteries)

if __name__ == '__main__':
    main()
