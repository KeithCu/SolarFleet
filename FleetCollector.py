from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import sys
import time
import requests
import pandas as pd
from sqlalchemy import PrimaryKeyConstraint, create_engine, Column, String, Float, DateTime, Integer, Float, Boolean

from sqlalchemy.orm import sessionmaker, declarative_base
from webdriver_manager.chrome import ChromeDriverManager

# Database setup using SQLAlchemy
DATABASE_URL = "sqlite:///solar_alerts.db"
Base = declarative_base()
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)

# Define tables
class Alert(Base):
    __tablename__ = "alerts"
    vendor_code = Column(String(3), nullable=False)
    site_id = Column(String, nullable=False)
    
    alert_type = Column(String, nullable=False)
    message    = Column(String, nullable=False)

    site_url   = Column(String, nullable=False)
    timestamp  = Column(DateTime, default=datetime.utcnow)
    resolved   = Column(DateTime, nullable=True)
    history    = Column(String, default="")  # Track changes/updates

    __table_args__ = (
        PrimaryKeyConstraint('vendor_code', 'site_id'),
    )

class Battery(Base):
    __tablename__ = "batteries"
    vendor_code = Column(String(3), nullable=False)
    site_id = Column(String, nullable=False)
    serial_number = Column(String, nullable=False)

    model_number = Column(String, nullable=False)
    state_of_energy = Column(Float, nullable=True)

    site_url   = Column(String, nullable=False)
    last_updated = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        PrimaryKeyConstraint('vendor_code', 'site_id', 'serial_number'),
    )

# Battery Data Update Function
def update_battery_data(vendor_code, site_id, serial_number, model_number, state_of_energy, site_url):
    session = SessionLocal()
    
    existing_battery = session.query(Battery).filter(
        Battery.vendor_code == vendor_code,
        Battery.site_id == site_id,
        Battery.serial_number == serial_number
    ).first()
    
    if existing_battery:
        existing_battery.state_of_energy = state_of_energy
        existing_battery.last_updated = datetime.utcnow()
    else:
        new_battery = Battery(
            vendor_code=vendor_code,
            site_id=site_id,
            serial_number=serial_number,
            model_number=model_number,
            state_of_energy=state_of_energy,
            site_url=site_url,
            last_updated=datetime.utcnow()
        )
        session.add(new_battery)
    
    session.commit()
    session.close()


def fetch_alerts(active_only=True):
    session = SessionLocal()
    query = session.query(Alert)
    if active_only:
        query = query.filter(Alert.resolved == False)
    alerts = pd.read_sql(query.statement, session.bind)
    session.close()
    return alerts

def fetch_low_batteries():
    session = SessionLocal()
    query = session.query(Battery).filter((Battery.state_of_energy < 0.10) | (Battery.state_of_energy.is_(None)))
    low_batteries = pd.read_sql(query.statement, session.bind)
    session.close()
    return low_batteries

def fetch_all_batteries():
    session = SessionLocal()
    query = session.query(Battery).order_by(Battery.state_of_energy.asc())
    all_batteries = pd.read_sql(query.statement, session.bind)
    session.close()
    return all_batteries

def add_alert(inverter, alert_type, message):
    session = SessionLocal()
    new_alert = Alert(inverter=inverter, alert_type=alert_type, message=message)
    session.add(new_alert)
    session.commit()
    session.close()


# Initialize database
def init_fleet_db():
    Base.metadata.create_all(engine)

def is_data_recent():
    """Check if any site has been updated within the last day."""
    session = SessionLocal()
    recent_battery = session.query(Battery).order_by(Battery.last_updated.desc()).first()
    session.close()

def update_alert_history(vendor_code, system_id, alert_type, message):
    pass

def add_alert_if_not_exists(vendor_code, system_id, message, alert_type, site_url):
    # Use a context manager to ensure the session is closed properly
    with SessionLocal() as session:
        # Query for an existing alert that is unresolved (resolved is NULL)
        existing_alert = session.query(Alert).filter(
            Alert.vendor_code == vendor_code,
            Alert.system_id == system_id,
            Alert.alert_type == alert_type,
            Alert.message == message,
            Alert.resolved.is_(None)  # Check for unresolved alerts (i.e., NULL)
        ).first()

        if not existing_alert:
            now = datetime.utcnow()
            history_message = (f"Alert created at {now.isoformat()} UTC; "
                               f"Type: '{alert_type}'; Message: '{message}'.")
            
            new_alert = Alert(
                vendor_code=vendor_code,
                system_id=system_id,
                alert_type=alert_type,
                message=message,
                site_url=site_url,  # Assuming inverter has a site_url attribute
                timestamp=datetime.utcnow(),
                resolved=None,  # No resolution date means it's unresolved
                history=history_message,
            )
            session.add(new_alert)
            session.commit()


from SolarEdge import SolarEdgePlatform

def collect_all():

#    platform = SolarEdgePlatform()

    if False and is_data_recent():
        print("Skipping updates as data is recent enough.")
        return

    # sites = platform.get_sites()

    # # Loop over each site to test the battery SoC retrieval robustly.
    # print("\nTesting get_batteries_soc() API call for each site:")
    # for site in sites:
    #     site_id = site['id']
    #     site_name = site['name']
    #     print(f"\nSite ID: {site_id} - {site['name']}")
    #     try:
    #         batteries = platform.get_batteries_soc(site_id)
    #         update_battery_data(site_id, site_name, batteries)

    #         if batteries:
    #             for battery in batteries:
    #                 soc = battery.get('state_of_energy')
    #                 print(f"  Battery Serial Number: {battery.get('serial_number')}, "
    #                       f"Model: {battery.get('model_number')}, "
    #                       f"SoC: {soc if soc is not None else 'N/A'}")
    #         else:
    #             print("  No battery data found for this site.")
    #     except Exception as e:
    #         print(f"  Error fetching battery data for site {site_id}: {e}")


if __name__ == '__main__':
    collect_all()
