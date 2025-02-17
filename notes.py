# Notes to myself:

# to do:

#     dedicated logging library

# 4. Bulk Operations
#     Bulk Insert/Update for Production Data: 
#         session.bulk_save_objects(new_production_records)
#         session.commit()
# 5. Data Consistency and Sanity Checks

#     Sanity Checks in process_bulk_solar_production: 
#         Re-enable the commented-out sanity check to ensure you're not storing production data on cloudy days unless explicitly recalibrating:


# 6. Database Design

#     Materialized View for Historical Data: 
#         If you often summarize daily production, consider a materialized view for this purpose:

#         sql

#         CREATE MATERIALIZED VIEW daily_production_summary AS
#         SELECT production_day, SUM(total_noon_kw) as total_production
#         FROM productionhistory
#         GROUP BY production_day;


# 7. Error Handling and Logging

#     Improve error handling in database operations. 
# Use try-except blocks with specific exceptions where appropriate to handle and log errors more gracefully. 
# # Helper Functions

#Features to add:

# Show number of API calls made in last 30 days for each service.

# Gather historical data for each site?

# Implement checking for low production compared to reference sites?

# Config settings and page? should it be page or a button?

# config settings: api keys, ?

# Sol-Ark: get production data besides live-time
# AP-Smart
# SMA
# Generac
# Goodwe
# Solis
# Solax

# Analytics and Reporting
# Add daily/weekly/monthly production comparison charts
# Export functionality for reports in CSV/PDF formats
# Performance metrics like efficiency ratios and target vs actual production
# Weather data correlation with production data
# Revenue calculations based on production data
# Monitoring Enhancements
# Real-time power flow visualization
# Battery charge/discharge cycle tracking
# Inverter efficiency monitoring
# Panel-level performance tracking
# Temperature monitoring for key components
# Alert System Improvements
# Email/SMS notification system for critical alerts
# Alert history and resolution tracking
# Custom alert thresholds configuration
# Alert prioritization system
# Scheduled maintenance notifications
# User Experience
# Dark/light mode toggle
# Customizable dashboard layouts
# Saved views/favorites for frequently monitored sites
# Mobile-responsive design improvements
# Interactive tooltips with detailed information
# Administrative Features
# User role management (admin, technician, viewer)
# Audit logs for user actions
# API usage tracking and quotas
# Backup and restore functionality
# System health monitoring
# Data Management
# Data cleanup tools
# Historical data archiving
# Data validation rules
# Automated data quality checks
# Data import/export tools
# Integration Features
# Weather API integration
# Calendar integration for maintenance scheduling
# Mobile app integration
# Third-party monitoring system integration
# Documentation/knowledge base integration
# Performance Optimization
# Data caching system
# Lazy loading for large datasets
# Background task processing
# Database query optimization
# API request batching
# Visualization Enhancements
# 3D site visualization
# Heat maps for production patterns
# Custom chart types
# Interactive graphs
# Time-lapse visualizations
# Maintenance Features
# Maintenance schedule tracking
# Service history logging
# Part replacement tracking
# Warranty information management
# Technician assignment system
# Financial Features
# ROI calculations
# Energy cost savings tracking
# Maintenance cost tracking
# Revenue forecasting
# Budget planning tools
# Security Enhancements
# Two-factor authentication
# Session management
# IP whitelisting
# Access control lists
# Security audit logging


from datetime import datetime
from sqlalchemy import (
    PrimaryKeyConstraint, create_engine, Column, String, Float, 
    DateTime, Integer, Date, ForeignKey, JSON, Index
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship

Base = declarative_base()

class Site(Base):
    __tablename__ = "sites"
    site_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    url = Column(String, nullable=False)
    nearest_site_id = Column(String, ForeignKey('sites.site_id'))
    nearest_distance = Column(String, nullable=False)
    
    # Relationships
    batteries = relationship("Battery", back_populates="site")
    metrics = relationship("SiteMetrics", back_populates="site")

class Battery(Base):
    __tablename__ = "batteries"
    site_id = Column(String, ForeignKey('sites.site_id'), primary_key=True)
    serial_number = Column(String, primary_key=True)
    model_number = Column(String, nullable=False)
    
    # Relationship
    site = relationship("Site", back_populates="batteries")
    metrics = relationship("BatteryMetrics", back_populates="battery")

# Metrics tables for time-series data
class SiteMetrics(Base):
    __tablename__ = "site_metrics"
    site_id = Column(String, ForeignKey('sites.site_id'), primary_key=True)
    timestamp = Column(DateTime, primary_key=True)
    inverter_values = Column(JSON)  # [inv1, inv2, total]
    
    site = relationship("Site", back_populates="metrics")
    
    __table_args__ = (
        Index('idx_site_metrics_timestamp', 'timestamp'),
    )

class BatteryMetrics(Base):
    __tablename__ = "battery_metrics"
    site_id = Column(String, ForeignKey('sites.site_id'), primary_key=True)
    serial_number = Column(String, ForeignKey('batteries.serial_number'), primary_key=True)
    timestamp = Column(DateTime, primary_key=True)
    state_of_energy = Column(Float)
    
    battery = relationship("Battery", back_populates="metrics")
    
    __table_args__ = (
        Index('idx_battery_metrics_timestamp', 'timestamp'),
    )

# Daily rollups for historical analysis
class DailyProduction(Base):
    __tablename__ = "daily_production"
    date = Column(Date, primary_key=True)
    site_id = Column(String, ForeignKey('sites.site_id'), primary_key=True)
    total_kwh = Column(Float, nullable=False)
    peak_kw = Column(Float, nullable=False)
    inverter_totals = Column(JSON)  # Daily totals per inverter
    
    __table_args__ = (
        Index('idx_daily_prod_date', 'date'),
    )

class Alert(Base):
    __tablename__ = "alerts"
    alert_id = Column(Integer, primary_key=True)
    site_id = Column(String, ForeignKey('sites.site_id'))
    alert_type = Column(String, nullable=False)
    details = Column(String, nullable=False)
    severity = Column(Integer, nullable=False)
    first_triggered = Column(DateTime, nullable=False)
    resolved_date = Column(DateTime)
    
    __table_args__ = (
        Index('idx_alerts_site', 'site_id'),
        Index('idx_alerts_triggered', 'first_triggered'),
    )
