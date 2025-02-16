# ☀️ Solar Fleet Monitoring Dashboard

![Dashboard Screenshot](https://github.com/user-attachments/assets/22b17fd1-0431-4813-90ca-c010ec9318f9)

A **real-time solar fleet monitoring** dashboard built with **Streamlit**, integrating multiple solar APIs, intelligent caching, and even web scraping for systems without official API support.

---

## 📌 Features

### ✅ **Multi-Source Data Integration**
- **SolarEdge v2 API** – Fully supported
- **Enphase v4 (Partner API)** – Near-complete integration
- **Sol-Ark** – Integrated (battery monitoring supported, alerts in progress)
- **Future support planned** for **Sonnen, SMA, AP-Smart**, and others

### ⚡ **Smart API Caching**
- Minimizes API costs and reduces redundant requests
- Uses intelligent expiration based on data frequency (1 hour to 1 month)
- Auto-refreshes stale data dynamically

### 📊 **Fleet Monitoring Dashboard**
- **Live solar production metrics** across all connected sites
- **Real-time alerts** for production failures, communication faults, and configuration issues
- **Battery monitoring** (SOC, model, serial number)
- **Historical data visualization** with Altair charts
- **Map view** for geographic distribution of sites

### 🔧 **Web Scraping for Non-API Systems**
- Uses **Selenium** for extracting data when no API is available (currently used for Sol-Ark)

---

## 💡 Why This Matters: The Problem with Existing Solar Monitoring

### ❌ The Old Way: Scattered, Slow, and Frustrating
Managing a solar fleet with multiple sites across different platforms is **a nightmare**. Here’s what you typically have to deal with:

- **Logging into multiple monitoring portals** (SolarEdge, Enphase, Sol-Ark, etc.)
- **Waiting for slow dashboards** to load (some take **15+ seconds** just to open!)
- **Hunting for problems manually**—for example, a site might be producing **35kW**, but **one inverter is down**, and you wouldn’t even notice unless you dig into each system one by one.
- **No site history**—you forget which sites had past issues, making troubleshooting harder.

### ✅ The New Way: A Unified Service Dashboard
This project eliminates **all** those frustrations by providing a **single dashboard** that gives you a **real-time overview** of your entire fleet. You get:

- **Instant access to all sites** across multiple platforms (no need to visit multiple portals)
- **Fast problem identification**—alerts show **which inverter is down**, instead of making you guess
- **Historical tracking**—view **site history** and past issues for better troubleshooting
- **Automated alerts**—get notified the moment something goes wrong

### 🚀 No Other Dashboard Like This
Most solar platforms only show **their own data**. **This dashboard is unique** because:
- It **integrates multiple vendors** into **one** place
- It **saves time** by removing the need to log into multiple sites
- It provides **historical context**—so you know if an issue **just started** or has been happening for **months**

---

## 🚀 Installation

### Prerequisites
- **Python 3.x**
- **Streamlit**
- **Selenium** (if using web scraping)
- Other dependencies listed in `requirements.txt`

### Setup Steps
1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/solar-fleet-dashboard.git
   cd solar-fleet-dashboard
## 2. Install Dependencies

```bash
pip install -r requirements.txt
```

## 3. Run the Streamlit Dashboard

```bash
streamlit run Dashboard.py
```

---

## 🔍 API Support Details

| Platform   | Status | Features |
|------------|--------|----------|
| **SolarEdge v2** | ✅ Complete | Site production, alerts, battery monitoring |
| **Enphase v4** | 🔄 Near Complete | Real-time production, battery state-of-energy (SOC), alerts |
| **Sol-Ark** | ✅ Integrated | Battery monitoring via Selenium (alerts coming soon) |
| **Future Integrations** | 📌 Planned | Sonnen, SMA, AP-Smart, and more |

---

## 🔮 Future Enhancements

- 🔧 **Complete Sol-Ark Alerts Integration**
- 📈 **Support for additional solar inverters & batteries**
- 🌎 **Improved geographic analytics for production trends**
- 📬 **Automated email alerts for system failures**
- ⚙️ **Performance optimizations & database indexing**

---

## 🤝 Contributing

**Want to improve the project?** Contributions are welcome!  
- **Fork the repository**  
- **Make your improvements**  
- **Submit a pull request** 🚀  

---

## 📜 License

This project is licensed under the **MIT License**.

---

## 🙌 Acknowledgements

Special thanks to:
- [Streamlit](https://streamlit.io/) for the awesome UI framework
- **SolarEdge, Enphase, Sol-Ark APIs** for providing solar data

---
