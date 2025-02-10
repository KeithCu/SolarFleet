from datetime import datetime
import SqlModels as Sql
import SolarPlatform
import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

def add_alert_if_not_exists(vendor_code, site_id, site_name, site_url, alert_type, details, severity, first_triggered):
    # Use a context manager to ensure the session is closed properly
    with Sql.SessionLocal() as session:
        # Query for an existing alert that is unresolved (resolved is NULL)
        existing_alert = session.query(Sql.Alert).filter(
            Sql.Alert.vendor_code == vendor_code,
            Sql.Alert.site_id == site_id,
            Sql.Alert.alert_type == alert_type,
            Sql.Alert.resolved_date.is_(None)  # Check for unresolved alerts (i.e., NULL)
        ).first()

        if not existing_alert:
            now = datetime.utcnow()
            history_message = (f"Notes: ")
            
            new_alert = Sql.Alert(
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

def fetch_production_data():
    session = Sql.SessionLocal()
    query = session.query(Sql.Production)
    production_data = pd.read_sql(query.statement, session.bind)
    session.close()
    return production_data

def update_battery_data(vendor_code, site_id, serial_number, model_number, state_of_energy, site_url):
    session = Sql.SessionLocal()
    
    existing_battery = session.query(Sql.Battery).filter(
        Sql.Battery.vendor_code == vendor_code,
        Sql.Battery.site_id == site_id,
        Sql.Battery.serial_number == serial_number
    ).first()
    
    if existing_battery:
        existing_battery.state_of_energy = state_of_energy
        existing_battery.last_updated = datetime.utcnow()
    else:
        new_battery = Sql.Battery(
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

# Battery Data Update Function
def fetch_alerts(active_only=True):
    session = Sql.SessionLocal()

    query = session.query(Sql.Alert).filter(Sql.Alert.alert_type != "SNOW_ON_SITE")
    # if active_only:
    #     query = query.filter(Alert.resolved == False)
    alerts = pd.read_sql(query.statement, session.bind)
    session.close()
    return alerts

def fetch_low_batteries():
    session = Sql.SessionLocal()
    query = session.query(Sql.Battery).filter((Sql.Battery.state_of_energy < 0.10) | (Sql.Battery.state_of_energy.is_(None)))
    low_batteries = pd.read_sql(query.statement, session.bind)
    session.close()
    return low_batteries

def fetch_all_batteries():
    session = Sql.SessionLocal()
    query = session.query(Sql.Battery).order_by(Sql.Battery.state_of_energy.asc())
    all_batteries = pd.read_sql(query.statement, session.bind)
    session.close()
    return all_batteries

def add_alert(inverter, alert_type, message):
    session = Sql.SessionLocal()
    new_alert = Sql.Alert(inverter=inverter, alert_type=alert_type, message=message)
    session.add(new_alert)
    session.commit()
    session.close()

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
    production_data: list[SolarPlatform.SolarProduction], 
    recalibrate: bool = False, 
    sunny_threshold: float = 100.0
):

    session = Sql.SessionLocal()

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
    existing_entries = session.query(Sql.Production).all()
    existing_dict = {(rec.vendor_code, rec.site_id): rec for rec in existing_entries}
    
    # Build a combined dataset (existing + new) with computed coordinates.
    combined = []
    # Process existing records.
    for rec in existing_entries:
        lat, lon = SolarPlatform.get_coordinates(rec.zip_code)
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
            lat, lon = SolarPlatform.get_coordinates(rec["zip_code"])
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
            lat, lon = SolarPlatform.get_coordinates(rec["zip_code"])
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
        new_entry = Sql.Production(
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
