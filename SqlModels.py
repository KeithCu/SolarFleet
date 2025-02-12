from datetime import datetime
from sqlalchemy import PrimaryKeyConstraint, create_engine, Column, String, Float, DateTime, Integer, Float, Date
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.types import PickleType

DATABASE_URL = "sqlite:///solar_alerts.db"
Base = declarative_base()
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)

#
# Define tables

class Site(Base):
    __tablename__ = "sites"
    site_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    url   = Column(String, nullable=False)

    history    = Column(String, default="")  # Track alert history

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
    details    = Column(String, nullable=False)
    severity   = Column(Integer, nullable=False)

    first_triggered  = Column(DateTime, default=datetime.utcnow)
    resolved_date   = Column(DateTime, nullable=True)

    __table_args__ = (
        PrimaryKeyConstraint('site_id', 'alert_type'),
    )
    
class ProductionHistory(Base):
    __tablename__ = "productionhistory"
    production_day = Column(Date, primary_key=True)
    #stores a set of SolarPlatform.ProductionRecord, one for each site
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
