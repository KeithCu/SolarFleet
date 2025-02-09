from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import List
import sys
import math
import time
import requests
import pandas as pd
from sqlalchemy import PrimaryKeyConstraint, create_engine, Column, String, Float, DateTime, Integer, Float, Boolean

from sqlalchemy.orm import sessionmaker, declarative_base
from webdriver_manager.chrome import ChromeDriverManager

import pgeocode
nomi = pgeocode.Nominatim('us')

import SolarPlatform

# Database setup using SQLAlchemy
DATABASE_URL = "sqlite:///solar_alerts.db"
Base = declarative_base()
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)

#
# Define tables
# This is a superset of SolarPlatform.SolarAlert

class Alert(Base):
    __tablename__ = "alerts"
    vendor_code = Column(String(3), nullable=False)
    site_id = Column(String, nullable=False)
    site_name = Column(String, nullable=False)
    site_url   = Column(String, nullable=False)
    
    alert_type = Column(String, nullable=False)
    details    = Column(String, nullable=False)
    severity   = Column(Integer, nullable=False)

    first_triggered  = Column(DateTime, default=datetime.utcnow)
    resolved_date   = Column(DateTime, nullable=True)
    history    = Column(String, default="")  # Track changes/updates

    __table_args__ = (
        PrimaryKeyConstraint('vendor_code', 'site_id', 'alert_type'),
    )

def add_alert_if_not_exists(vendor_code, site_id, site_name, site_url, alert_type, details, severity, first_triggered):
    # Use a context manager to ensure the session is closed properly
    with SessionLocal() as session:
        # Query for an existing alert that is unresolved (resolved is NULL)
        existing_alert = session.query(Alert).filter(
            Alert.vendor_code == vendor_code,
            Alert.site_id == site_id,
            Alert.alert_type == alert_type,
            Alert.resolved_date.is_(None)  # Check for unresolved alerts (i.e., NULL)
        ).first()

        if not existing_alert:
            now = datetime.utcnow()
            history_message = (f"Notes: ")
            
            new_alert = Alert(
                vendor_code = vendor_code,
                site_id = site_id,
                site_name = site_name,
                site_url = site_url,
                alert_type = alert_type,
                details = details,
                severity = severity,
                first_triggered = first_triggered,
                resolved_date = None,  # No resolution date means it's unresolved
                history = history_message,
            )
            session.add(new_alert)
            session.commit()


class Production(Base):
    __tablename__ = "production"
    vendor_code = Column(String(3), nullable=False)
    site_id = Column(String, nullable=False)
    zip_code = Column(String, nullable=False)

    nearest_vendor_code = Column(String(3), nullable=False)
    nearest_site_id = Column(String, nullable=False)
    nearest_distance = Column(String, nullable=False)

    noon_production = Column(Float, nullable=True)
    site_url   = Column(String, nullable=False)
    last_updated = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        PrimaryKeyConstraint('vendor_code', 'site_id', ),
    )


def haversine_distance(lat1, lon1, lat2, lon2):

    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    return c * 3958.8  # Earth radius in miles

def get_coordinates(zip_code):
    result = nomi.query_postal_code(zip_code)
    if result is None or math.isnan(result.latitude):
        return None, None
    return result.latitude, result.longitude

# Bulk process a list of SolarProduction data. 

# Parameters:
#   - production_data: list of SolarProduction records.
#   - recalibrate: if True, override sanity checks (used when calibrating on a known sunny day).
#   - sunny_threshold: expected minimum average production on a sunny day.

# Behavior:
#   1. Computes the average production across all new records.
#      - If the average is below sunny_threshold and recalibrate is False, the function
#        refuses to update (to avoid cloudy-day corruption).
#   2. For each record, it checks if an entry (by vendor_code and site_id) already exists:
#      - If so, it updates the production and timestamp.
#      - Otherwise, it adds it as a new entry.
#   3. For new entries, it builds a combined dataset (existing + new) and uses a BallTree
#      (with the haversine metric) to compute for each new site the nearest neighbor’s vendor_code,
#      site_id, and distance (in miles). These values are stored in the new record.

def process_bulk_solar_production(
    production_data: list[SolarProduction], 
    recalibrate: bool = False, 
    sunny_threshold: float = 100.0
):

    session = SessionLocal()

    if not production_data:
        print("No production data provided.")
        return

    # Compute average production for sanity check.
    avg_prod = sum(prod.site_production for prod in production_data) / len(production_data)
    if avg_prod < sunny_threshold and not recalibrate:
        raise ValueError(
            f"Average production ({avg_prod:.2f}) is below the sunny threshold ({sunny_threshold}). "
            "Data rejected to prevent calibration on a cloudy day."
        )
    
    # For these solar entries, use a default vendor_code (or derive it as needed).
    default_vendor_code = "SOL"

    # Convert SolarProduction objects to dictionaries suitable for our Production model.
    new_records = []
    for prod in production_data:
        new_records.append({
            "vendor_code": default_vendor_code,
            "site_id": prod.site_id,
            "zip_code": str(prod.site_zipcode),
            "noon_production": prod.site_production,
            "site_url": prod.site_url
        })
    
    # Query existing Production entries.
    existing_entries = session.query(Production).all()
    existing_dict = {(rec.vendor_code, rec.site_id): rec for rec in existing_entries}
    
    # Build a combined dataset (existing + new) with computed coordinates.
    combined = []
    # Process existing records.
    for rec in existing_entries:
        lat, lon = get_coordinates(rec.zip_code)
        if lat is None:
            continue
        combined.append({
            "vendor_code": rec.vendor_code,
            "site_id": rec.site_id,
            "zip_code": rec.zip_code,
            "lat": lat,
            "lon": lon,
            "noon_production": rec.noon_production,
            "site_url": rec.site_url
        })
    
    # Process new records.
    new_to_insert = []
    for rec in new_records:
        key = (rec["vendor_code"], rec["site_id"])
        if key in existing_dict:
            # Update the existing record (avoid recalculation).
            existing = existing_dict[key]
            existing.noon_production = rec["noon_production"]
            existing.last_updated = datetime.utcnow()
            session.commit()
            # Add to combined dataset.
            lat, lon = get_coordinates(rec["zip_code"])
            if lat is not None:
                combined.append({
                    "vendor_code": existing.vendor_code,
                    "site_id": existing.site_id,
                    "zip_code": existing.zip_code,
                    "lat": lat,
                    "lon": lon,
                    "noon_production": existing.noon_production,
                    "site_url": existing.site_url
                })
        else:
            # New record: compute its coordinates.
            lat, lon = get_coordinates(rec["zip_code"])
            if lat is None:
                continue
            rec["lat"] = lat
            rec["lon"] = lon
            new_to_insert.append(rec)
            combined.append(rec)
    
    # If there are new records, build a BallTree over the combined dataset.
    if new_to_insert:
        coords = np.array([[r["lat"], r["lon"]] for r in combined])
        coords_rad = np.radians(coords)
        tree = BallTree(coords_rad, metric='haversine')
        keys = [(r["vendor_code"], r["site_id"]) for r in combined]
        
        # For each new record, compute the nearest neighbor.
        for rec in new_to_insert:
            new_key = (rec["vendor_code"], rec["site_id"])
            query_point = np.radians(np.array([[rec["lat"], rec["lon"]]]))
            dist_rad, ind = tree.query(query_point, k=2)
            # If the closest neighbor is itself, take the second closest.
            if keys[ind[0][0]] == new_key and len(ind[0]) > 1:
                nearest_idx = ind[0][1]
                distance_miles = dist_rad[0][1] * 3958.8
            else:
                nearest_idx = ind[0][0]
                distance_miles = dist_rad[0][0] * 3958.8
            rec["nearest_vendor_code"] = keys[nearest_idx][0]
            rec["nearest_site_id"] = keys[nearest_idx][1]
            rec["nearest_distance"] = int(round(distance_miles))
    
    # Bulk insert new records.
    for rec in new_to_insert:
        new_entry = Production(
            vendor_code=rec["vendor_code"],
            site_id=rec["site_id"],
            zip_code=rec["zip_code"],
            noon_production=rec["noon_production"],
            site_url=rec["site_url"],
            nearest_vendor_code=rec.get("nearest_vendor_code", rec["vendor_code"]),
            nearest_site_id=rec.get("nearest_site_id", rec["site_id"]),
            nearest_distance=rec.get("nearest_distance", 0),
            last_updated=datetime.utcnow()
        )
        session.add(new_entry)
    session.commit()
    print(f"Processed {len(new_records)} records. Average production: {avg_prod:.2f}")

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

    query = session.query(Alert).filter(Alert.alert_type != "SNOW_ON_SITE")
    # if active_only:
    #     query = query.filter(Alert.resolved == False)
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



from SolarEdge import SolarEdgePlatform


def collect_platform(platform):
    platform.log("Testing get_sites_map() API call...")
    try:
        sites = platform.get_sites_map()
        for site_id in sites.keys():
            battery_data = platform.get_batteries_soe(site_id)
            for battery in battery_data:                    
                update_battery_data(platform.get_vendorcode(), site_id, battery['serialNumber'], battery['model'], battery['stateOfEnergy'], "")
                platform.log(f"Site {site_id} Battery Data: {battery_data}")
    except Exception as e:
        platform.log(f"Error while fetching sites: {e}")
        return
    try:
        alerts = platform.get_alerts() 
        for alert in alerts:
            add_alert_if_not_exists(platform.get_vendorcode(), alert.site_id, alert.site_name, 
                                    alert.site_url, alert.alert_type, alert.details, alert.severity, alert.first_triggered)

    except Exception as e:
        platform.log(f"Error while fetching alerts: {e}")
        return


def collect_all():

#    platform = SolarEdgePlatform()

    if False and is_data_recent():
        print("Skipping updates as data is recent enough.")
        return

    # sites = platform.get_sites_map()

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
