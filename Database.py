from datetime import datetime, date
from typing import List, Tuple

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree
from sqlalchemy.orm.attributes import flag_modified

import SqlModels as Sql
import SolarPlatform


def add_site_if_not_exists(site_id):
    session = Sql.SessionLocal()

    existing_site = session.query(Sql.Site).filter_by(site_id=site_id).first()

    if existing_site:
        session.close()
        return existing_site

    new_site = Sql.Site(
        site_id=site_id,
        history="Notes: ",
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


def add_alert_if_not_exists(site_id, alert_type, details, severity, first_triggered):
    now = SolarPlatform.get_now()

    with Sql.SessionLocal() as session:
        existing_alert = session.query(Sql.Alert).filter(
            Sql.Alert.site_id == site_id,
            Sql.Alert.alert_type == alert_type,
            # Check for unresolved alerts (i.e., NULL)
            Sql.Alert.resolved_date.is_(None)
        ).first()

        if not existing_alert:

            new_alert = Sql.Alert(
                site_id=site_id,
                alert_type=str(alert_type),
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
        existing_battery.last_updated = SolarPlatform.get_now()
    else: 
        new_battery = Sql.Battery(
            site_id= site_id,
            serial_number = serial_number,
            model_number = model_number,
            state_of_energy = state_of_energy,
            last_updated = SolarPlatform.get_now()
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
    Sql.Alert.__table__.drop(bind=Sql.engine, checkfirst=True)


def fetch_low_batteries():
    session = Sql.SessionLocal()
    query = session.query(Sql.Battery).filter(
        (Sql.Battery.state_of_energy < 10) | (Sql.Battery.state_of_energy.is_(None)))
    low_batteries = pd.read_sql(query.statement, session.bind)
    session.close()
    return low_batteries


def fetch_all_batteries():
    session = Sql.SessionLocal()
    query = session.query(Sql.Battery).order_by(
        Sql.Battery.state_of_energy.asc())
    all_batteries = pd.read_sql(query.statement, session.bind)
    session.close()
    return all_batteries

def delete_all_batteries():
    session = Sql.SessionLocal()
    try:
        session.query(Sql.Battery).delete()
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def get_valid_production_dates():
    historical_production_df = get_total_noon_kw()
    if not historical_production_df.empty:
        valid_dates = historical_production_df['production_day'].tolist()
        return valid_dates
    else:
        return [datetime.now().date()]
    
def get_total_noon_kw() -> pd.DataFrame:
    session = Sql.SessionLocal()
    try:
        results = session.query(
            Sql.ProductionHistory.production_day,
            Sql.ProductionHistory.total_noon_kw
        ).all()
        df = pd.DataFrame(results, columns=['production_day', 'total_noon_kw'])
        return df
    finally:
        session.close()


def get_production_set(production_day: date = None) -> set:
    session = Sql.SessionLocal()
    try:
        query = session.query(Sql.ProductionHistory)
        if production_day is None:
            record = query.order_by(Sql.ProductionHistory.production_day.desc()).first()
        else:
            production_date = production_day
            record = query.filter_by(production_day=production_date).first()

        if record:
            return record.data
        return set()
    finally:
        session.close()


def insert_or_update_production_set(new_data: set[SolarPlatform.ProductionRecord], production_day):
    session = Sql.SessionLocal()
    try:
        existing_record = session.get(Sql.ProductionHistory, production_day)

        if existing_record:
            # Build a dictionary from the existing set keyed by site_id
            data_dict = {record.site_id: record for record in existing_record.data}
            # Update or add new records; this replaces records with matching site_id
            for record in new_data:
                data_dict[record.site_id] = record
            # Replace the set with the updated records
            existing_record.data = set(data_dict.values())
            flag_modified(existing_record, "data")
            session.add(existing_record)
        else:
            existing_record = Sql.ProductionHistory(production_day=production_day, data=new_data)
            session.add(existing_record)

        # Calculate total noon production (using the updated data)
        total_noon_kw = sum(SolarPlatform.calculate_production_kw(site.production_kw) for site in existing_record.data)
        existing_record.total_noon_kw = total_noon_kw

        session.commit()
        return existing_record

    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

def process_bulk_solar_production(
        reference_date: date,
        production_data: set[SolarPlatform.ProductionRecord],
        recalibrate: bool = False,
        sunny_threshold: float = 100.0):

    if not production_data:
        print("No production data provided.")
        return

    # Compute average production for sanity check.
    production_kw = 0.0
    for site in production_data:
        production_kw += SolarPlatform.calculate_production_kw(site.production_kw)

    avg_prod = production_kw / len(production_data)
    # if avg_prod < sunny_threshold and not recalibrate:
    #     raise ValueError(
    #         f"Average production ({avg_prod:.2f}) is below the sunny threshold ({sunny_threshold}). "
    #         "Data rejected to prevent calibration on a cloudy day."
    #     )

    insert_or_update_production_set(production_data, reference_date)

    print(f"Processed {len(production_data)} records. Average production: {avg_prod:.2f}")
