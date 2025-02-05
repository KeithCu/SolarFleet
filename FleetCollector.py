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

from SolarPlatform import Battery, Alert

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

from SolarEdge import SolarEdgePlatform

def main():
    init_db()

    platform = SolarEdgePlatform()

    if False and is_data_recent():
        print("Skipping updates as data is recent enough.")
        return

    sites = platform.get_sites()

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

    # Fetch SolarEdge alerts
    print("\nFetching alerts and other info for each site:")
    for site in sites:
        site_id = site['id']
        print(f"\nSite ID: {site_id} - {site['name']}")
        try:
            alerts = platform.get_alerts(site_id)
            for alert in alerts:
                if alert > 0:
                    add_alert_if_not_exists("SolarEdge", site_id, alert)
            else:
                print("No alerts found for this site.")
        except Exception as e:
            print(f"Error while fetching alerts for site {site_id}: {e}")

if __name__ == '__main__':
    main()
