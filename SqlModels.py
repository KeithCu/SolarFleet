from datetime import datetime
from sqlalchemy import PrimaryKeyConstraint, create_engine, Column, String, Float, DateTime, Integer, Float, Boolean
from sqlalchemy.orm import sessionmaker, declarative_base

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

def init_fleet_db():
    Base.metadata.create_all(engine)
