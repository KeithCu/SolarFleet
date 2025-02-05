import streamlit as st
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime, timedelta
import pandas as pd

from SolarPlatform import Alert, Battery

# Database setup using SQLAlchemy
DATABASE_URL = "sqlite:///solar_alerts.db"
Base = declarative_base()
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)

def send_browser_notification(title, message):
    js_code = f"""
    if ("Notification" in window) {{
        if (Notification.permission === "granted") {{
            new Notification("{title}", {{ body: "{message}" }});
        }} else if (Notification.permission !== "denied") {{
            Notification.requestPermission().then(permission => {{
                if (permission === "granted") {{
                    new Notification("{title}", {{ body: "{message}" }});
                }}
            }});
        }}
    }}
    """
    st.components.v1.html(f"<script>{js_code}</script>", height=0)

# Initialize database
def init_db():
    Base.metadata.create_all(engine)

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
    query = session.query(Battery).filter(Battery.state_of_energy_1 < 10)
    low_batteries = pd.read_sql(query.statement, session.bind)
    session.close()
    return low_batteries

def fetch_all_batteries():
    session = SessionLocal()
    query = session.query(Battery).order_by(Battery.state_of_energy_1.asc())
    all_batteries = pd.read_sql(query.statement, session.bind)
    session.close()
    return all_batteries

def add_alert(inverter, alert_type, message):
    session = SessionLocal()
    new_alert = Alert(inverter=inverter, alert_type=alert_type, message=message)
    session.add(new_alert)
    session.commit()
    session.close()

# Streamlit UI
st.set_page_config(page_title="Absolute Solar Monitoring", layout="wide")
st.title("☀️ Absolute Solar Monitoring Dashboard ☀️")
st.markdown("---")
init_db()

col1, col2 = st.columns(2)

with col1:
    st.header("🚨 Active Alerts")
    alerts_df = fetch_alerts()
    if not alerts_df.empty:
        st.dataframe(alerts_df, height=300)
    else:
        st.success("No active alerts.")
    
    with st.expander("Add New Alert"):
        inverter = st.text_input("Inverter ID")
        alert_type = st.text_input("Alert Type")
        message = st.text_area("Message")
        if st.button("Submit Alert"):
            add_alert(inverter, alert_type, message)
            st.experimental_rerun()

with col2:
    st.header("🔋 Batteries Below 10%")
    low_batteries_df = fetch_low_batteries()
    if not low_batteries_df.empty:
        st.dataframe(low_batteries_df, height=300)
    else:
        st.success("All batteries above 10%.")
    
    with st.expander("🔋 Full Battery List (Sorted by SOC, Hidden by Default)"):
        all_batteries_df = fetch_all_batteries()
        if not all_batteries_df.empty:
            st.dataframe(all_batteries_df, height=400)
        else:
            st.success("No battery data available.")
