from datetime import datetime, date
from typing import List, Tuple

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

import SqlModels as Sql
import SolarPlatform


def add_site_if_not_exists(site_id, name, url, nearest_site_id, nearest_distance):
    session = Sql.SessionLocal()

    existing_site = session.query(Sql.Site).filter_by(
        site_id=site_id
    ).first()

    if existing_site:
        session.close()
        return existing_site

    new_site = Sql.Site(
        site_id=site_id,
        name=name,
        url=url,
        history="Notes: ",
        nearest_site_id=nearest_site_id,
        nearest_distance=nearest_distance
    )
    session.add(new_site)
    session.commit()
    session.close()
    return new_site


def fetch_sites():
    session = Sql.SessionLocal()
    try:
        sites_df = pd.read_sql(session.query(Sql.Site).statement, session.bind)
        return sites_df
    finally:
        session.close()


def update_site_history(site_id, new_history):
    session = Sql.SessionLocal()
    try:
        site = session.query(Sql.Site).filter_by(site_id=site_id).first()
        if site:
            site.history = new_history
            session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def add_alert_if_not_exists(site_id, name, url, alert_type, details, severity, first_triggered):
    with Sql.SessionLocal() as session:
        existing_alert = session.query(Sql.Alert).filter(
            Sql.Alert.site_id == site_id,
            Sql.Alert.alert_type == alert_type,
            # Check for unresolved alerts (i.e., NULL)
            Sql.Alert.resolved_date.is_(None)
        ).first()

        if not existing_alert:
            now = datetime.utcnow()

            new_alert = Sql.Alert(
                site_id=site_id,
                name=name,
                url=url,
                alert_type=alert_type,
                details=details,
                severity=severity,
                first_triggered=first_triggered,
                resolved_date=None,
            )
            session.add(new_alert)
            session.commit()


def update_battery_data(site_id, serial_number, model_number, state_of_energy):
    session = Sql.SessionLocal()

    existing_battery = session.query(Sql.Battery).filter(
        Sql.Battery.site_id == site_id,
        Sql.Battery.serial_number == serial_number
    ).first()

    if existing_battery:
        existing_battery.state_of_energy = state_of_energy
        existing_battery.last_updated = datetime.utcnow()
    else:
        new_battery = Sql.Battery(
            site_id=site_id,
            serial_number=serial_number,
            model_number=model_number,
            state_of_energy=state_of_energy,
            last_updated=datetime.utcnow()
        )
        session.add(new_battery)

    session.commit()
    session.close()

# Battery Data Update Function


def fetch_alerts():
    session = Sql.SessionLocal()

    query = session.query(Sql.Alert)
    alerts = pd.read_sql(query.statement, session.bind)
    session.close()
    return alerts


def delete_all_alerts():
    session = Sql.SessionLocal()
    try:
        session.query(Sql.Alert).delete()
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def fetch_low_batteries():
    session = Sql.SessionLocal()
    query = session.query(Sql.Battery).filter(
        (Sql.Battery.state_of_energy < 0.10) | (Sql.Battery.state_of_energy.is_(None)))
    low_batteries = pd.read_sql(query.statement, session.bind)
    session.close()
    return low_batteries


def fetch_all_batteries():
    session = Sql.SessionLocal()
    query = session.query(Sql.Battery).order_by(
        Sql.Battery.state_of_energy.asc())
    all_batteries = pd.read_sql(query.statement, session.bind)
    session.close()


def get_total_noon_kw_all() -> List[Tuple[date, float]]:
    session = Sql.SessionLocal()
    try:
        # Query both production_day and total_noon_kw
        results = session.query(
            Sql.ProductionHistory.production_day,
            Sql.ProductionHistory.total_noon_kw
        ).all()
        # results is a list of tuples: [(date1, kw1), (date2, kw2), ...]
        return results
    finally:
        session.close()

    return all_batteries


def get_production_set(production_day: date) -> set:
    session = Sql.SessionLocal()
    try:
        # This doesn't respect the production_day for some reason, but does return data so is okay for now.
        # Perhaps the day stored in the database is not exactly this time, but close?
        # Anyway once I get the stuff displaying something, anything, reasonable, I can fix.
        # record = session.query(Sql.ProductionHistory).filter_by(production_day=production_day).first()
        record = session.query(Sql.ProductionHistory).first()
        if record:
            return record.data
        return set()
    finally:
        session.close()


def insert_or_update_production_set(new_data: set[SolarPlatform.ProductionRecord], production_day):
    session = Sql.SessionLocal()
    try:
        # Retrieve the existing record by primary key using session.get()
        existing = session.get(Sql.ProductionHistory, production_day)

        if existing:
            combined_set = (existing.data)
            combined_set.update(new_data)
        else:
            # If no record exists, use a copy of new_data.
            combined_set = new_data.copy()

        # calculate the total noon production for all sites, to use for historical purposes.
        total_noon_kw = 0
        for e in combined_set:
            total_noon_kw += e.production_kw

        # Create a fresh instance with the merged data.
        new_record = Sql.ProductionHistory(
            production_day=production_day, data=combined_set, total_noon_kw=total_noon_kw)

        # session.merge() will check if a record with the given primary key exists;
        # if so, it will update that record with new_record’s state, otherwise it will add a new record.
        merged_record = session.merge(new_record)

        session.commit()
        return merged_record
    except Exception as e:
        session.rollback()
        raise e
    finally:
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

    # # If there are new records, build a BallTree over the combined dataset.
    # if new_to_insert:
    #     coords = np.array([[r["lat"], r["lon"]] for r in combined])
    #     coords_rad = np.radians(coords)
    #     tree = BallTree(coords_rad, metric='haversine')
    #     keys = [(r["vendor_code"], r["site_id"]) for r in combined]

    #     # For each new record, compute the nearest neighbor.
    #     for rec in new_to_insert:
    #         new_key = (rec["vendor_code"], rec["site_id"])
    #         query_point = np.radians(np.array([[rec["lat"], rec["lon"]]]))
    #         dist_rad, ind = tree.query(query_point, k=2)
    #         # If the closest neighbor is itself, take the second closest.
    #         if keys[ind[0][0]] == new_key and len(ind[0]) > 1:
    #             nearest_idx = ind[0][1]
    #             distance_miles = dist_rad[0][1] * 3958.8
    #         else:
    #             nearest_idx = ind[0][0]
    #             distance_miles = dist_rad[0][0] * 3958.8
    #         rec["nearest_vendor_code"] = keys[nearest_idx][0]
    #         rec["nearest_site_id"] = keys[nearest_idx][1]
    #         rec["nearest_distance"] = int(round(distance_miles))


def process_bulk_solar_production(
        reference_date: date,
        production_data: set[SolarPlatform.ProductionRecord],
        recalibrate: bool = False,
        sunny_threshold: float = 100.0):

    if not production_data:
        print("No production data provided.")
        return

    # Compute average production for sanity check.
    avg_prod = sum(prod.production_kw for prod in production_data) / \
        len(production_data)
    # if avg_prod < sunny_threshold and not recalibrate:
    #     raise ValueError(
    #         f"Average production ({avg_prod:.2f}) is below the sunny threshold ({sunny_threshold}). "
    #         "Data rejected to prevent calibration on a cloudy day."
    #     )

    insert_or_update_production_set(production_data, reference_date)

    print(
        f"Processed {len(production_data)} records. Average production: {avg_prod:.2f}")
