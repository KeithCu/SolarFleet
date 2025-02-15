from datetime import datetime
from sqlalchemy import PrimaryKeyConstraint, create_engine, Column, String, Float, DateTime, Integer, Float, Date
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.types import PickleType

DATABASE_URL = "sqlite:///solar_alerts.db"
Base = declarative_base()
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)

#
# # Define tables

# Given that you're not storing latitude and longitude in the database, here's how you can add the other indexes using SQLAlchemy:

# python

# from sqlalchemy import Index

# # For Alerts Table
# Index('idx_alerts_first_triggered', Alert.first_triggered)
# Index('idx_alerts_type', Alert.alert_type)

# # For ProductionHistory Table
# Index('idx_productionhistory_day', ProductionHistory.production_day)


# Add these Index objects to your table definitions:

# python

# class Alert(Base):
#     __tablename__ = "alerts"
#     # ... existing columns ...
#     __table_args__ = (
#         Index('idx_alerts_first_triggered', 'first_triggered'),
#         Index('idx_alerts_type', 'alert_type'),
#     )

# class ProductionHistory(Base):
#     __tablename__ = "productionhistory"
#     # ... existing columns ...
#     __table_args__ = (
#         Index('idx_productionhistory_day', 'production_day'),
#     )


# Bug in get_production_set
# Regarding the issue with get_production_set, here are potential causes and solutions:

#     Date vs. Datetime Mismatch:
#         SQLite might store dates as TEXT or DATETIME, which can lead to type mismatches if not handled correctly.

#     Check how production_day is stored in SQLite:

#         If it's stored as a string in a specific format, ensure your date object is converted to match this format before querying:

#         python

# from datetime import date, datetime

# def get_production_set(production_day: date) -> set:
#     session = Sql.SessionLocal()
#     try:
#         # Assuming SQLite stores dates as 'YYYY-MM-DD'
#         date_str = production_day.strftime('%Y-%m-%d')
#         record = session.query(Sql.ProductionHistory).filter_by(production_day=date_str).first()
#         if record:
#             return record.data
#         return set()
#     finally:
#         session.close()

# If production_day is stored as a DATETIME in SQLite, you might need to compare against a range:

# python

#     def get_production_set(production_day: date) -> set:
#         session = Sql.SessionLocal()
#         try:
#             start_of_day = datetime.combine(production_day, time.min)
#             end_of_day = datetime.combine(production_day, time.max)
#             record = session.query(Sql.ProductionHistory).filter(
#                 Sql.ProductionHistory.production_day.between(start_of_day, end_of_day)
#             ).first()
#             if record:
#                 return record.data
#             return set()
#         finally:
#             session.close()

# SQLAlchemy Version or SQLite Issue: Sometimes, the way SQLAlchemy interprets date comparisons can lead to unexpected behavior, especially with different SQLite versions. You might want to:

#     Check your SQLAlchemy and SQLite versions for known bugs or compatibility issues.
#     Print or log the SQL statement SQLAlchemy generates for debugging:

#     python

#     from sqlalchemy import inspect

#     inspector = inspect(session.bind)
#     print(inspector.get_columns('productionhistory'))
#     # Print the generated SQL for debugging
#     print(session.query(Sql.ProductionHistory).filter_by(production_day=production_day).statement)

# Data Inspection: Make sure the data in your database matches what you're querying for:

#     Query directly with SQL or through SQLAlchemy to see if there's data for that day:

#     python

# with Sql.SessionLocal() as session:
#     result = session.execute(select(Sql.ProductionHistory.production_day))
#     for row in result:
#         print(row.production_day)  # See if it matches your query date

class Site(Base):
    __tablename__ = "sites"
    site_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    url = Column(String, nullable=False)

    history = Column(String, default="")  # Track alert history

    nearest_site_id = Column(String, nullable=False)
    nearest_distance = Column(String, nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint('site_id'),
    )


class Alert(Base):
    __tablename__ = "alerts"
    site_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    url = Column(String, nullable=False)

    alert_type = Column(String, nullable=False)
    details = Column(String, nullable=False)
    severity = Column(Integer, nullable=False)

    first_triggered = Column(DateTime, nullable=False)
    resolved_date = Column(DateTime, nullable=True)

    __table_args__ = (
        PrimaryKeyConstraint('site_id', 'alert_type'),
    )


class ProductionHistory(Base):
    __tablename__ = "productionhistory"
    production_day = Column(Date, primary_key=True)
    # stores a set of SolarPlatform.ProductionRecord, one for each site
    data = Column(PickleType, nullable=False)
    total_noon_kw = Column(Float, nullable=False)


class Battery(Base):
    __tablename__ = "batteries"
    site_id = Column(String, nullable=False)
    serial_number = Column(String, nullable=False)

    model_number = Column(String, nullable=False)
    state_of_energy = Column(Float, nullable=True)

    last_updated = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        PrimaryKeyConstraint('site_id', 'serial_number'),
    )


def init_fleet_db():
    Base.metadata.create_all(engine)
